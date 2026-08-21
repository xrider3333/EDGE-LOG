# NOISE — wide-band intraday momentum envelope: lockbox findings & open questions

> Living handoff doc. **Last updated: 2026-08-21** (COMBINATION study — the "ultimate
> crown" question. Clean NEGATIVE: nothing clears the pre-registered bar, and the BROADER
> day-type filter combines WORSE than the narrower one. See the "2026-08-21 — combination
> study" section, regenerable via tools/noise_combo_study.py).
> Prior update **2026-08-18** (TRADE CONTEXT feature scan — clean
> negative, nothing new survived — see the "2026-08-18 — TRADE CONTEXT feature→PnL scan"
> section, regenerable via tools/noise_context_scan.py).
> Prior update **2026-08-17** (variant campaign session — see the
> "2026-08-17 — variant campaign" section: pre-registered entry-quality filters cleared
> the bar; knobs shipped in `NOISE_1_0.py`; 12-cell comparison GRID + full re-validate + first NOISE BOOK job queued;
> the "Campaign results table" subsection carries every config with IS/WF/LB dollar
> splits + drawdown, regenerable via tools/noise_campaign_table.py; the "PnL attribution"
> and "ES-transfer comparison" subsections explain WHAT DROVE each variant trade-by-trade
> and rank the ES sibling, regenerable via tools/noise_attribution.py).
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

### PnL attribution — WHAT DROVE each variant, trade by trade

> Built 2026-08-17 by `tools/noise_attribution.py` (committed the same day). Regenerate:
> `python tools/noise_attribution.py` (add `--check` for the gates only, `--json out.json`
> for the raw numbers). Same PINNED source as the table above: db_noadj_rth · NQ 5m RTH ·
> cost 0.533 pts · multiplier 20. It refuses to print anything unless **16/16 rows of the
> campaign table above reproduce to the dollar** (they do) **and** every variant's
> decomposition ties back to its own net delta (it does).

**How to read the decomposition.** Each variant's trade list is diffed against the #231
champion's, trade by trade, and the net delta is split three ways:

- **REMOVED** — a champion trade the variant never enters.
- **ADDED** — a variant trade the champion never enters. These are real: blocking an entry
  leaves the strategy FLAT, so a later signal in the same session that the champion slept
  through (it was already in a position) now gets taken. **A pure-veto filter is not purely
  subtractive**, which is why "PnL of the removed trades" only *approximately* equals the
  delta for the veto filters and not at all for `confirm_bars`.
- **ALTERED** — same entry, different exit. **Zero for every variant here** — these are all
  entry filters and none of them touches an exit.

`−removed + added + altered = net delta` holds exactly (to the dollar) on all 8 variants ×
both windows. That is the tie-back gate.

**Two mechanisms, never compare them as if they were one:**

- **VETO** (`daytype_mode`, `vol_skip_pct`) — the trade is cut and never comes back. Removed
  ≈ the whole story.
- **DELAY** (`confirm_bars`) — the same session signal fires N bars later at a worse price,
  so nearly every trade shows up as one REMOVED plus one ADDED. On the selection window
  `confirm_bars=2` removes 3,783 and adds back 2,680. Reading its "removed PnL" as the
  driver would be flatly wrong.

#### Attribution — SELECTION window 2010-06-07 → 2025-02-10 (pre-lockbox; where the bar was set)

| Variant | trades | net $ | PF | MAR | Δ net $ | Δ long $ | Δ short $ | removed (L/S) | avg of removed | mech | **what drove it** |
|---|---|---|---|---|---|---|---|---|---|---|---|
| #231 champion (baseline) | 5,113 | 277,123 | 1.24 | 14.22 | — | — | — | — | — | — | — |
| `skip_bot_short` | 4,748 | 320,530 | 1.31 | 17.27 | **+43,407** | +587 | **+42,820** | 366 (2/364) | −$120 | veto | cuts 364 shorts that averaged −$118 each, only 30% of them winners; **98.6% of the gain is the short side**, spread over 13 up-years |
| `skip_bot_short` + `vol_skip 90` | 4,054 | 320,130 | 1.42 | 17.38 | +43,007 | +27,559 | +15,448 | 1,059 (535/524) | −$41 | veto | two vetoes overlapping on the same bad days — adds nothing to `skip_bot_short` alone (−$400) |
| `vol_skip 98` | 4,868 | 309,055 | 1.30 | 16.12 | +31,932 | +13,907 | +18,026 | 245 (172/73) | −$130 | veto | sits out 245 post-top-2%-vol trades; 83% of the gain is its 10 worst avoided trades |
| **`confirm2` + `skip_bot_short` (D3 WINNER)** | 4,010 | **332,699** | 1.40 | **23.64** | **+55,576** | +20,773 | +34,803 | 3,783 rm / 2,680 add | n/a (delay) | delay+veto | the short-side veto (+$34.8k) plus a 2-bar entry delay that fires late but cheaper; **best DD of the set, −$5,406** |
| `vol_skip 95` | 4,697 | 302,963 | 1.31 | 15.80 | +25,839 | +18,890 | +6,950 | 416 (279/137) | −$62 | veto | 10 avoided trades ARE the whole gain (103%) — ex those 10 it is −$898 |
| `vol_skip 90` | 4,309 | 310,690 | 1.37 | 16.32 | +33,566 | +27,559 | +6,008 | 804 (535/269) | −$42 | veto | 86% from 10 trades, 55% from 2024 alone; only 7 up-years vs 8 down-years |
| `skip_top_long` (DEAD) | 4,091 | 226,473 | 1.24 | 9.58 | **−50,651** | −50,651 | 0 | 1,022 (1,022/0) | **+$50** | veto | throws away 1,022 LONGS that were *profitable* (+$50 each) — it cuts the money side; DD also gets WORSE (+$4,165) |
| `confirm_bars 2` alone | 4,309 | 299,099 | 1.32 | 16.45 | +21,976 | +20,773 | +1,203 | 3,704 rm / 2,900 add | n/a (delay) | delay | a pure delay: it re-enters 2,900 of the 3,704 it skipped, 2 bars later; the +$22.0k is what the late entries saved on the days that reversed |

#### Attribution — FULL window 2010-06-07 → 2026-08-12 (includes the SPENT lockbox)

| Variant | trades | net $ | PF | MAR | Δ net $ | Δ long $ | Δ short $ | removed | **what changed vs the selection window** |
|---|---|---|---|---|---|---|---|---|---|
| #231 champion | 5,633 | 335,981 | 1.22 | 10.25 | — | — | — | — | — |
| `skip_bot_short` | 5,214 | 388,181 | 1.29 | 12.45 | **+52,200** | +587 | **+51,613** | 420 (2/418) | **HOLDS and grows** — 418 shorts at −$123 avg, +14 up-years vs 3 down |
| `skip_bot_short` + `vol_skip 90` | 4,429 | 380,745 | 1.39 | 17.23 | +44,764 | +12,912 | +31,852 | 1,204 | holds; 92% of it is 10 trades |
| `vol_skip 98` | 5,347 | 384,690 | 1.29 | 17.22 | +48,709 | +12,352 | +36,357 | 286 | grows, but 2026 alone is +$17,912 of it |
| **`confirm2` + `skip_bot_short` (D3)** | 4,418 | 367,959 | 1.32 | 9.75 | +31,978 | +9,658 | +22,321 | 4,164 rm / 2,949 add | **shrinks by $23.6k** — the 2025 give-back; DD goes the WRONG way (+$4,935) |
| `vol_skip 95` | 5,159 | 375,262 | 1.30 | 13.00 | +39,281 | +10,469 | +28,812 | 474 | grows; still 96% from 10 trades |
| `vol_skip 90` | 4,732 | 372,285 | 1.35 | 15.71 | +36,304 | +12,912 | +23,392 | 901 | grows; 111% from 10 trades |
| `skip_top_long` (DEAD) | 4,527 | 280,710 | 1.22 | 8.05 | −55,271 | −55,271 | 0 | 1,106 | worse still |
| `confirm_bars 2` alone | 4,762 | 320,914 | 1.25 | **7.26** | **−15,067** | +9,658 | −24,724 | 4,072 rm / 3,201 add | **flips NEGATIVE** — 2025 alone is −$35,487 |

#### Δ by year ($) — selection window, then the two lockbox years

| Variant | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BASELINE net | −2,278 | 1,719 | −433 | −53 | 6,264 | 4,671 | −150 | 1,784 | 40,068 | 3,393 | 29,052 | 35,060 | 66,447 | 29,487 | 56,349 | 29,152 | 35,449 |
| `skip_bot_short` | +344 | +3,330 | +780 | +196 | +2,478 | −911 | +2,305 | −277 | +3,579 | +855 | +9,536 | +8,234 | +9,558 | +11,060 | −11,018 | +11,550 | +599 |
| `skip_bot_short`+`vs90` | +344 | −1,537 | +1,016 | −1,019 | +658 | +798 | +8,572 | −1,052 | −10,798 | −1,655 | +2,879 | +3,159 | +18,595 | +14,150 | +6,175 | +4,379 | +102 |
| `vol_skip 98` | 0 | −935 | +138 | +295 | +652 | +3,777 | +2,205 | +904 | +11,767 | 0 | +5,861 | +572 | +589 | 0 | +6,108 | −1,135 | +17,912 |
| **D3 WINNER** | +696 | +2,108 | +2,009 | +1,346 | +1,272 | −2,821 | +5,802 | +325 | +4,529 | +8,532 | +5,473 | +348 | +17,306 | +11,554 | −2,485 | **−20,771** | −3,245 |
| `vol_skip 95` | 0 | −1,857 | +256 | −461 | +1,267 | +1,068 | +5,008 | −436 | +143 | 0 | +1,883 | −2,093 | +9,672 | 0 | +11,390 | +5,455 | +7,987 |
| `vol_skip 90` | 0 | −2,777 | +236 | −878 | −1,259 | +2,667 | +9,506 | −1,052 | −11,429 | −1,946 | +1,092 | −2,071 | +17,903 | +5,605 | +18,602 | +2,603 | −497 |
| `skip_top_long` (DEAD) | +1,213 | −564 | +1,022 | +63 | −2,148 | +4,406 | +572 | +919 | −3,636 | −5,860 | +11,714 | **−20,464** | **−19,156** | +1,480 | **−21,216** | +8,276 | −11,893 |
| `confirm_bars 2` (DEAD) | +153 | −848 | +1,130 | +820 | −1,618 | −3,281 | +3,794 | +858 | +3,627 | +10,212 | −8,057 | −5,606 | +12,266 | +2,584 | +9,380 | **−35,487** | −4,994 |

Dominant years, in one line each:

- **`skip_bot_short`** — no single year carries it: 2023 (+11.1k), 2025 (+11.6k), 2020 (+9.5k),
  2022 (+9.6k), 2021 (+8.2k), against one bad year 2024 (−11.0k). **Positive in 14 of 17 years.**
- **`vol_skip` family** — 2024 and 2022 (and 2026 for the 98 threshold). 2018–2019 are
  *negative* for the 90/95 thresholds: the filter sits out days that were good.
- **D3 winner** — 2022 (+17.3k) and 2023 (+11.6k) pre-lockbox; then **2025 −20.8k**.
- **`skip_top_long`** — kills 2021 (−20.5k), 2022 (−19.2k), 2024 (−21.2k): every big long year.
- **`confirm_bars 2`** — 2019 and 2022 pre-lockbox; **2025 −35.5k** wipes all of it out.

#### Drawdown attribution

**The champion's worst stretch, selection window: 2022-01-13 → 2022-01-28** (the January 2022
top), 20 trades, −$14,638, MaxDD $19,482. What each variant did across those exact dates:

| Variant | own MaxDD $ | Δ DD $ | PnL across the champion's worst stretch | trades it removed inside it |
|---|---|---|---|---|
| `skip_bot_short` | 18,560 | −922 | −10,308 | 7 (worth −$4,330) |
| `skip_bot_short`+`vs90` | 18,425 | −1,058 | **+4,384** | 18 (worth −$19,022) |
| `vol_skip 98` | 19,176 | −306 | −7,651 | 6 (−$6,987) |
| **D3 WINNER** | **14,076** | **−5,406** | −11,202 | 18 (−$13,877) |
| `vol_skip 95` | 19,176 | −306 | −2,768 | 11 (−$11,870) |
| `vol_skip 90` | 19,041 | −441 | **+4,384** | 18 (−$19,022) |
| `skip_top_long` | 23,647 | **+4,165** | −14,638 | 0 |
| `confirm_bars 2` | 18,180 | −1,302 | −15,306 | 18 (−$13,877) |

- **Yes, the DD improvement is a specific stretch.** The `vol_skip` filters turn January 2022
  from −$14.6k into **+$4.4k** by sitting out 18 trades — but their MaxDD barely moves
  (−$306 to −$441), because their own worst stretch is a *different* one (Aug 2023 → Dec 2023).
  Fixing one drawdown does not fix the deepest one.
- **D3 is the only variant that improves the deepest drawdown itself** (−$5,406, DD $14,076),
  and it does it inside that same January-2022 window.

**On the FULL window the picture inverts, and this is the single most important finding in
this subsection.** The champion's worst stretch becomes **2026-06-09 → 2026-07-27** (−$27,340,
DD $32,794). There:

| Variant | own MaxDD $ | Δ DD $ | own worst stretch | variant $ across it | baseline $ across the same dates |
|---|---|---|---|---|---|
| `skip_bot_short` | 31,191 | −1,603 | 2026-06-09 → 2026-07-24 | −25,737 | −25,284 |
| `skip_bot_short`+`vs90` | 22,096 | **−10,698** | 2026-06-16 → 2026-07-29 | −16,136 | −18,313 |
| `vol_skip 98` | 22,334 | −10,460 | 2026-06-16 → 2026-07-27 | −16,374 | −18,496 |
| **D3 WINNER** | **37,729** | **+4,935** | **2025-03-03 → 2025-04-09** | **−33,755** | −23,654 |
| `vol_skip 95` | 28,873 | −3,921 | 2026-06-16 → 2026-07-27 | −22,914 | −18,496 |
| `vol_skip 90` | 23,698 | −9,096 | 2026-06-16 → 2026-07-29 | −17,739 | −18,313 |
| `skip_top_long` | 34,882 | +2,088 | 2026-06-09 → 2026-07-27 | −29,428 | −27,340 |
| **`confirm_bars 2`** | **44,189** | **+11,395** | **2025-03-03 → 2025-04-09** | **−40,214** | −23,654 |

**Why `confirm_bars 2` alone owns the worst drawdown in the whole grid ($44,189) on FEWER
trades — answered.** Its entire extra drawdown is one stretch, **2025-03-03 → 2025-04-09**
(the spring-2025 selloff), where it loses **−$40,214** against the champion's −$23,654 over
the same dates — a $16.6k *self-inflicted* hole in a window the champion handled better. The
mechanism is exactly the knob's definition: waiting for a second confirming close means
entering one bar later, and one bar is worth the most precisely on the largest-range days.
On fast expansion days the delay hands back the best part of the move and then pays the same
bandwidth stop. Fewer trades, but each one entered at a worse price on the days that matter
most. **D3 inherits this** — its full-window DD ($37,729) also comes from that same
March–April 2025 stretch, not from anything the `skip_bot_short` leg does.

#### Incremental view — what each combo adds ON TOP of its own components

| Combo | measured against | Δ net $ (selection) | Δ net $ (full) | dominant years (full) |
|---|---|---|---|---|
| D3 (`confirm2`+`skip_bot_short`) | `confirm_bars 2` alone | **+33,600** | **+47,045** | 2025 +14.7k, 2020 +13.5k |
| D3 (`confirm2`+`skip_bot_short`) | `skip_bot_short` alone | +12,169 | **−20,221** | **2025 −32.3k** |
| `skip_bot_short`+`vs90` | `vol_skip 90` alone | +9,441 | +8,460 | 2024 −12.4k, 2023 +8.5k |
| `skip_bot_short`+`vs90` | `skip_bot_short` alone | **−400** | **−7,436** | 2024 +17.2k, 2018 −14.4k |

Read that top-to-bottom: **`skip_bot_short` is the load-bearing half of the winner, and the
`confirm_bars` half only ever added value inside the selection window.** Out of sample the
`confirm_bars` leg *subtracts* $20.2k. And `vol_skip 90` adds nothing to `skip_bot_short`
on either window (−$400 / −$7,436) — the two filters veto the same days, exactly as the
Occam combo rule concluded from the headline numbers alone.

#### Concentration — broad effect, or a handful of trades?

| Variant | Δ net $ | best single year | its share | 10 worst removed trades | their share | **Δ excluding those 10** | years +/− |
|---|---|---|---|---|---|---|---|
| `skip_bot_short` | +43,407 | 2023 +11,060 | 25% | +24,071 | 55% | **+19,335** | 13 / 3 |
| `skip_bot_short`+`vs90` | +43,007 | 2022 +18,595 | 43% | +29,697 | 69% | +13,310 | 11 / 5 |
| `vol_skip 98` | +31,932 | 2018 +11,767 | 37% | +26,452 | 83% | +5,480 | 11 / 1 |
| **D3 WINNER** | +55,576 | 2022 +17,306 | 31% | +32,364 | 58% | **+23,212** | 13 / 3 |
| `vol_skip 95` | +25,839 | 2024 +11,390 | 44% | +26,737 | **103%** | **−898** | 8 / 4 |
| `vol_skip 90` | +33,566 | 2024 +18,602 | 55% | +28,887 | 86% | +4,679 | 7 / 8 |
| `confirm_bars 2` | +21,976 | 2022 +12,266 | 56% | +32,364 | 147% | −10,389 | 10 / 6 |

(Selection window. Full-window shares are in the same direction and slightly worse for the
`vol_skip` family — 92%/96%/111% for 90/95/98.)

- **`vol_skip` is FRAGILE.** Strip its 10 luckiest avoidances and `vol_skip 95` is *negative*
  (−$898), `vol_skip 90` is +$4.7k over 794 remaining trades, `vol_skip 98` +$5.5k over 235.
  The threshold "trend" is also non-monotonic on the selection window (90: $310.7k, 98:
  $309.1k, 95: $303.0k) — that is noise, not a dose-response curve. `vol_skip 90` is positive
  in only **7 years and negative in 8**.
- **`skip_bot_short` is the broad one.** 55% top-10 share is the lowest of the veto filters,
  and stripping those 10 still leaves **+$19.3k spread across 356 remaining removed trades**,
  positive in **13 of 16 years** (14 of 17 on the full window). Its removed population is
  coherent, not a tail: 364 shorts, 30% win rate vs the strategy's own ~37%, average −$118.
- **`confirm_bars 2` is worse than fragile** — ex the 10 best avoided trades it is *negative*
  in-sample too (−$10,389), which is the same conclusion its out-of-sample collapse reaches.

### ES-transfer comparison across the campaign variants

> Independent arbiter, because NOISE's own lockbox is SPENT. Same code path, same knobs, on
> the **ES 5m RTH no-adj master** (`NOADJ_ES_5m_RTH.csv`, db_noadj_rth, 2010-06-07 →
> 2026-08-17), costs held at **0.533 pts/trade** — the campaign's own ES-probe convention.
> Points are the comparable unit; dollars are shown at the **ES multiplier 50** (NQ is 20),
> so ES $ and NQ $ are NOT directly comparable.
> **Cross-check: this reproduces the round log's ES probe exactly** — champion 645.0 pts /
> PF 1.036, D3 1,519.0 pts / PF 1.116.
>
> **Two different bars, and they are not interchangeable** (NOISE.md caveat 3): the engine's
> GENERIC cross-instrument sanity check is PF ≥ 1.0; **NOISE's OWN pre-registered promotion
> bar is PF ≥ 1.2**, and that is the one cited for promotion.

**Selection window 2010-06-07 → 2025-02-10, ranked by ES PF:**

| Rank | Variant | ES trades | ES net pts | ES net $ (×50) | ES PF | ES MaxDD $ | ES MAR | PF ≥ 1.0 (generic) | PF ≥ 1.2 (NOISE bar) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `skip_bot_short` + `vol_skip 90` | 4,134 | 1,451.3 | 72,565 | **1.126** | 21,482 | 3.38 | pass | **FAIL** |
| 2 | **D3 `confirm2`+`skip_bot_short`** | 4,133 | **1,519.0** | 75,951 | 1.116 | **13,868** | **5.48** | pass | **FAIL** |
| 3 | `vol_skip 90` | 4,390 | 1,260.5 | 63,027 | 1.100 | 32,210 | 1.96 | pass | FAIL |
| 4 | `skip_bot_short` | 4,900 | 1,424.4 | 71,222 | 1.093 | 24,217 | 2.94 | pass | FAIL |
| 5 | `vol_skip 95` | 4,795 | 1,273.4 | 63,669 | 1.090 | 29,793 | 2.14 | pass | FAIL |
| 6 | `vol_skip 98` | 5,023 | 1,052.2 | 52,608 | 1.068 | 31,138 | 1.69 | pass | FAIL |
| 7 | `confirm_bars 2` | 4,465 | 894.4 | 44,719 | 1.059 | 23,386 | 1.91 | pass | FAIL |
| 8 | **#231 champion (baseline)** | 5,312 | 645.0 | 32,250 | 1.036 | 41,480 | 0.78 | pass | FAIL |
| 9 | `skip_top_long` (DEAD) | 4,393 | 296.2 | 14,809 | 1.020 | 42,325 | 0.35 | pass | FAIL |

**Full window 2010-06-07 → 2026-08-12, ranked by ES PF:**

| Rank | Variant | ES trades | ES net pts | ES net $ (×50) | ES PF | ES MaxDD $ | ES MAR |
|---|---|---|---|---|---|---|---|
| 1 | `skip_bot_short` + `vol_skip 90` | 4,522 | 1,630.3 | 81,515 | **1.116** | 21,482 | 3.79 |
| 2 | D3 `confirm2`+`skip_bot_short` | 4,531 | 1,640.3 | 82,016 | 1.100 | 20,845 | 3.93 |
| 3 | **`skip_bot_short`** | 5,368 | **1,751.5** | **87,573** | 1.093 | 24,217 | 3.62 |
| 4 | `vol_skip 90` | 4,812 | 1,311.2 | 65,558 | 1.085 | 32,210 | 2.04 |
| 5 | `vol_skip 95` | 5,253 | 1,439.3 | 71,967 | 1.083 | 29,793 | 2.42 |
| 6 | `vol_skip 98` | 5,504 | 1,126.5 | 56,324 | 1.059 | 31,138 | 1.81 |
| 7 | `confirm_bars 2` | 4,900 | 926.0 | 46,299 | 1.050 | 23,386 | 1.98 |
| 8 | **#231 champion (baseline)** | 5,823 | 805.6 | 40,281 | 1.037 | 41,480 | 0.97 |
| 9 | `skip_top_long` (DEAD) | 4,823 | 257.8 | 12,888 | 1.014 | 42,325 | 0.30 |

- **Every filter variant improves ES transfer over the champion, on both windows.** The
  champion is 8th of 9 — only the DEAD `skip_top_long` is worse. That is genuine independent
  evidence the filters are not pure NQ curve-fit.
- **Best ES PF: `skip_bot_short` + `vol_skip 90`** (1.126 / 1.116). **Best ES points:
  `skip_bot_short` alone on the full window** (1,751.5 pts, +117% over the champion's 805.6)
  and D3 on the selection window (1,519.0, +136%).
- **ES drawdown falls too**: the champion's ES MaxDD $41,480 → $13,868 for D3, $21,482 for
  `skip_bot_short`+`vs90`. ES MAR goes from 0.78 → 5.48.
- **NOTHING clears NOISE's own PF ≥ 1.2 promotion bar.** Best is 1.126. Every variant clears
  the engine's generic PF ≥ 1.0 sanity check, but that is not the promotion gate. **NOISE
  still has never cleared its own ES-transfer requirement** — the campaign moves it from
  "1.036, barely alive" to "1.126, clearly directional", which is a meaningful shift in the
  same failing direction, not a pass.

### Robustness read — which variant has the best-EXPLAINED mechanism

1. **`daytype_mode='skip_bot_short'` is the robust one, and it is the only one this
   attribution actually endorses.** It is a clean veto with a coherent population (364–418
   shorts, 30% win rate against the strategy's own ~37%, −$120 average), it is positive in
   **14 of 17 years**, it survives stripping its 10 best avoidances (+$19.3k left over 356
   trades), it *improves* full-window drawdown (−$1,603) instead of trading one drawdown for
   another, it grows out of sample (+$43.4k selection → +$52.2k full), it nearly triples ES
   points (806 → 1,752), and its mechanism is a **program-wide banked pattern** — "shorts
   fail after weak closes", seen in 4+ families. Nothing about it is a small number of huge
   days.
   > **CORRECTION, 2026-08-18 — the "program-wide" claim in this bullet is WRONG and must not
   > be repeated.** The filter was finally built and tested on the two families that matter,
   > ORB (run #234, the live crown) and ENGU-Q, and it failed on both — full round log in
   > `CROSSFAMILY_DAYTYPE.md`. On ORB the mechanism is SIGN-FLIPPED: shorts after a weak close
   > average **+$86** per trade over 248 trades, where NOISE's lose $118. What DOES hold across
   > families is the other half of the pattern, "buy weakness": trades taken after a weak close
   > are the better population on ORB longs and dramatically so on ENGU-Q (+$462 per trade
   > versus +$31 after a strong close). Treat `skip_bot_short` as a NOISE-specific result.
2. **The D3 winner is really `skip_bot_short` plus a fragile passenger.** Measured against
   its own components, the `confirm_bars 2` leg adds +$12.2k inside the selection window and
   **−$20.2k outside it**, and it is the sole source of D3's full-window drawdown blow-out
   (2025-03-03 → 2025-04-09). D3's headline MAR 23.64 is real but window-specific.
3. **The `vol_skip` family is FRAGILE** — a small number of huge avoided days, not a broad
   effect. 83–103% of each threshold's improvement is its 10 worst avoided trades;
   `vol_skip 95` is *negative* without them; `vol_skip 90` is positive in only 7 of 15 years;
   the thresholds do not order monotonically. It should stay a banked single, never a
   crowned knob, and it should never be stacked on `skip_bot_short` (adds −$400 / −$7,436).
4. **`confirm_bars` should be dropped, not just left off.** Ex-top-10 it is negative
   in-sample, it flips to −$15.1k out of sample, and it owns the grid's worst drawdown by a
   mechanism that is structural rather than unlucky: a one-bar entry delay costs the most on
   the largest-range days, which are the days the strategy makes its money on.
5. **`skip_top_long` explains itself**: it removes 1,022–1,106 LONGS averaging **+$50**, and
   kills 2021/2022/2024 — the champion's three biggest long years. It is not a filter, it is
   an amputation of the profitable side.

**Suggested next step (not taken here — no runner jobs were queued):** re-run the
owner-visible arbiters with `skip_bot_short` ALONE as the candidate, rather than D3. It is
the leg carrying the mechanism, it is the leg that survives out of sample, and it is the leg
whose ES transfer improves most in dollars.

---

## 2026-08-18 — TRADE CONTEXT feature→PnL scan: the scan WORKS, and it finds nothing NEW to act on

> Closes the "TRADE CONTEXT feature→PnL FDR scan on NOISE" item in "Still genuinely
> untested". Code: `tools/noise_context_scan.py` (committed the same day). Regenerate:
> `python tools/noise_context_scan.py` (add `--json out.json` for the raw numbers,
> `--quick` for a 200-draw bootstrap). No runner jobs were queued — this is entirely local.
> Source PINNED to the campaign's convention: **db_noadj_rth · NQ 5m RTH · cost 0.533 pts ·
> multiplier 20 · 2010-06-07 → 2026-08-12**. Trade logs come from the parity-proven campaign
> harness `tools/noise_variant_research.py`; the statistics come from the SHIPPED, generic
> engine `augur_engine/context.py`, used exactly as the ORB scan used it — no bespoke method.

### What was scanned

Two configs × three sides = **six scans**, each over **16 features** = **96 tests total**.

- **CHAMPION** — run #231's crowned config (lookback 44, band 0.75/1.5, vwap exit, bandwidth
  stop k=1.75), every filter knob OFF. 5,633 trades over 2,785 entry days.
- **SBS** — the same core plus `daytype_mode='skip_bot_short'` (take no SHORT entries the day
  after a close in the bottom 20% of the prior day's range), the campaign's load-bearing
  variant. 5,214 trades. Scanning both answers a second question: does the filter ABSORB the
  effects the scan finds, or are independent effects left over?
- **Sides**: all trades, LONGS only, SHORTS only. The campaign's finding was 98.6% short-side,
  so a pooled-only scan could wash a real effect out.

**The 16 features.** Fifteen are the stock library, all prior-day shifted by the engine
(`gap_pct` is causal as defined — today's open against yesterday's close is known before any
fill). Eight are internal, from the run's own bars: `rsi14`, `macd_hist`, `atr20_pctile`,
`er20` (trend-vs-chop efficiency), `gap_pct`, `prev_ret`, `range_pctile`, `up_streak`. Seven
are external macro, from the offline CSV cache: `vix`, `vix_pctile_1y`, `vix_chg_5d`,
`vix_term`, `tnx`, `tnx_chg_20d`, `curve`.

**The 16th is `close_pos`, added for this scan** — the prior session's close position inside
its own high-low range, i.e. the exact quantity the campaign's `skip_bot_short` filter
compares against 0.2. It is NOT in the stock library, so **without adding it the scan could
not possibly have rediscovered the known day-type effect.** That is itself a finding about the
feature library, not about NOISE. It is scored like any other feature and counted in every
correction.

**The gates a feature must clear to be marked `survives`** (all four, the engine's own rules,
unchanged): Benjamini-Hochberg q < 0.10 across the features in its scan; a 95% confidence
interval from a MOVING-BLOCK bootstrap (contiguous 21–126 trading-day blocks, clustered by
entry day) that excludes zero; for slow/persistent features, a within-calendar-year
consistency test (|t| ≥ 2 across eras); and beating the strongest of three shadow probes
(shuffled fake features that set a per-dataset noise floor). On top of that, this scan
recomputes a **GLOBAL** Benjamini-Hochberg q across all 96 tests, because six scans of
sixteen features is ninety-six tests, not sixteen. Both q values are reported below.

### Sanity check — PASSED. The scan independently rediscovers the known day-type effect

Two independent confirmations, and they agree:

1. **Direct, single pre-specified hypothesis, day-clustered permutation test** (5,000 draws,
   whole days reshuffled so trades sharing a day move together): the champion's short trades
   entered the day after a bottom-20%-of-range close number **418**, they total
   **−$51,613**, they average **−$123.48** against **+$138.86** for the champion's other
   shorts, and the one-sided permutation p is **0.0004**. Those figures reproduce the
   2026-08-17 attribution table to the dollar (418 shorts, −$123 average, Δ short +$51,613),
   which is the parity gate on this whole exercise.
2. **The blind feature scan finds it too, on the right side and nowhere else.** On
   CHAMPION/short, `close_pos` has rho +0.0553, raw p 0.0199, within-scan q 0.0485, global q
   0.0347, and it clears all four gates. On CHAMPION/long it is nothing (rho +0.0207, p 0.20)
   — correctly one-sided. And on **SBS/short it is dead** (rho −0.0148, p 0.59): the
   `skip_bot_short` filter has absorbed the effect completely, which is exactly what a
   working filter should do to its own signal.

So the scan is not underpowered on NOISE. With 5,633 trades over 16 years it has roughly ten
times the sample the ORB scan had (590 trades), and it detects a $52k effect blind.

### Results — what survived, and why none of it is new

| Scan | trades | survivors (all four gates) |
|---|---|---|
| CHAMPION / all | 5,633 | vix · range_pctile · atr20_pctile · vix_pctile_1y · vix_chg_5d · gap_pct · prev_ret · macd_hist · vix_term · rsi14 · **close_pos** · up_streak |
| CHAMPION / long | 3,864 | range_pctile · vix · atr20_pctile · gap_pct · vix_pctile_1y · vix_chg_5d · macd_hist · vix_term · rsi14 · prev_ret · up_streak |
| CHAMPION / short | 1,769 | vix · atr20_pctile · prev_ret · **close_pos** · vix_chg_5d |
| SBS / all | 5,214 | vix · range_pctile · gap_pct · vix_chg_5d · vix_pctile_1y |
| SBS / long | 3,863 | range_pctile · vix · atr20_pctile · gap_pct · vix_pctile_1y · vix_chg_5d · macd_hist · vix_term · rsi14 · prev_ret · up_streak |
| **SBS / short** | 1,351 | **NONE** |

Unlike ORB — where nothing survived at all — plenty survives here. That is a power story, not
a discovery story. **Every survivor falls into one of three already-known or already-rejected
buckets:**

**1. The stress cluster is the volatility effect the campaign already banked.** `vix`,
`vix_pctile_1y`, `vix_chg_5d`, `atr20_pctile` and `range_pctile` all carry the same sign —
trades entered after a high-volatility session earn less. `range_pctile` is the largest and
most era-consistent of them (CHAMPION/long rho −0.0926, era t −4.88). This is precisely the
mechanism the 2026-08-17 campaign found by hand and banked as `vol_skip 90` (day-clustered
permutation p 0.001 at the time). The scan re-derives it independently, which is a second
successful sanity check and not a new lead. The campaign already documented that this family
is FRAGILE in dollars (83–103% of each vol threshold's gain is its ten luckiest avoidances) —
nothing here changes that.

**2. `curve` and `tnx` are textbook drift artifacts, and the era guard caught them.** `curve`
has the largest raw correlation in every single scan (rho +0.10 to +0.14, raw p 0.0000) and
survives NOTHING, because its within-year t statistic is essentially zero (0.16, −0.38, 0.37,
−0.01). Both are flagged `trend_confounded` in five of six scans. Two things that drift over a
decade correlate whether or not one causes the other. This is the same false lead the ENGU-Q
work already documented, and it is the clearest evidence in the whole exercise that the
correction machinery is doing its job rather than rubber-stamping big numbers.

**3. `gap_pct` looked like the one genuinely new lead, and a follow-up audit kills it.** It is
the only feature that is jointly backed as well as univariately significant — LASSO keeps it
with a large coefficient AND it beats the random-forest probe floor, in all four scans where
it survives — and its within-year consistency is the highest in the whole run (era t 8.4 to
9.9). It is a LONG-side effect: long trades entered on a day that gapped DOWN earn less. The
raw dollars look interesting: on the champion, long trades entered after a gap down of 0.5% or
more number 139 and total **−$33,662**, against +$62.70 per trade for every other long.

**Then the overlap audit.** Of that −$33,662, **−$26,303 (78%) sits on days the already-banked
`vol_skip 90` filter would have skipped anyway**. The residual is 95 trades worth −$7,359,
whose ten worst trades alone are −$23,178 and which is negative in 8 years and positive in 9.
At a −0.25% gap threshold the residual is not even negative — it is **+$10,174**. A gap down
is mostly just a high-volatility day wearing a different hat. There is no independent
gap-down edge left once the known volatility effect is removed.

**Also worth stating plainly:** `prev_ret`, `macd_hist`, `rsi14`, `up_streak` and `vix_term`
survive with small correlations (rho +0.03 to +0.06) and all point the same way — NOISE does
better after strong prior days and worse after weak ones. That is the same "buy weakness /
shorts fail after weak closes" family the program has banked four times over, and
`close_pos`/`skip_bot_short` is already the cleanest expression of it. No separate knob is
implied.

### Does the SBS filter absorb what the scan finds?

Partly, and informatively. On the short side it absorbs everything: SBS/short has **zero**
survivors where CHAMPION/short had five. On the long side it changes almost nothing, which is
correct — `skip_bot_short` never touches long trades. The residual long-side survivors are the
volatility family, and the campaign already established that stacking `vol_skip 90` on
`skip_bot_short` adds nothing in dollars (−$400 on the selection window, −$7,436 on the full
window). The scan and the campaign agree: the two filters veto the same days.

### VERDICT — nothing new survives. Do not build a variant off this.

- **The scan is trustworthy and adequately powered on NOISE.** It rediscovered a $52k effect
  blind, on the correct side, and watched that effect vanish once the filter that targets it
  was switched on.
- **Nothing survived correction that is not already explained** by the two banked mechanisms —
  the volatility effect (`vol_skip`, banked as a fragile single) and the weak-close effect
  (`skip_bot_short`, the campaign's load-bearing filter).
- **`gap_pct` was the one candidate and it does not stand up.** 78% of its dollars are already
  inside `vol_skip 90`, the residual is tail-driven and sign-unstable across years, and at a
  looser threshold the residual flips positive.
- **`curve` and `tnx` must never be quoted from a raw p-value.** They are the biggest raw
  correlations in the run and they are drift.

**If the owner ever wants to spend a pre-registered test on the gap idea anyway**, this is
what it would have to look like, declared in full before any backtest: candidate = block LONG
entries when the session gaps down more than X%, X ∈ {0.4, 0.5, 0.6} declared as the plateau
neighborhood; selection on the pre-lockbox window 2010-06-07 → 2025-02-10 only; bar = net ≥
champion AND MAR ≥ champion AND 2010-17 ≥ $0 AND worst year not worse AND all three X values
clear (a real plateau, not one lucky threshold); and a mandatory extra leg this scan has
already pre-failed — **the candidate must beat `vol_skip 90` as a standalone AND add net
dollars on top of `vol_skip 90`**, since 78% of its raw effect is the same days. On the
evidence above it will not clear that last leg, which is the honest reason not to spend the
test.

---

## 2026-08-21 — combination study ("the ultimate crown"): CLEAN NEGATIVE, nothing is crowned

> Harness: `tools/noise_combo_study.py` (committed this day). Regenerate the whole round with
> `python tools/noise_combo_study.py`; `--gate` runs the reproduction gate only. It sits on top of
> `tools/noise_variant_research.py`, whose parity against the real engine is already proven to the
> cent. Source PINNED: db_noadj_rth · NQ 5m RTH · cost_pts 0.533 · multiplier 20 · 1 contract.
> ES sibling: the ES 5m RTH no-adjust master, same knobs, nothing refitted, multiplier 50.
> **No runner job was queued. The runner was not restarted. No data master was imported or refreshed.**

**The question.** Three NOISE variants have now passed full validation on run #231's exact window
and all three beat the crowned champion: **run #241** = skip SHORT trades the day after a weak
close (`NOISE_1_1_SBS.py`), **run #245** = skip ALL trades the day after a weak close
(`NOISE_1_1_SBA.py`), **run #243** = skip shorts after a weak close PLUS skip the wildest 10% of
days (`NOISE_1_1_SBS_V90.py`). Can the features be COMBINED into something better than any of them?

**The genuine gap this round attacks.** The 2026-08-17 campaign only ever combined the NARROWER
shorts-only day-type filter, and only ever against volatility threshold 90. The BROADER day-type
filter (`skip_bot_all`) had never been combined with anything, and thresholds 95/98 had never been
paired with either day-type filter. That is the untested space, and it is where this round ran.
Note that "broader combined with narrower" is not a distinct experiment: `skip_bot_all` vetoes a
strict superset of what `skip_bot_short` vetoes on the same days, so the two are one knob with two
settings, not two stackable knobs.

### PRE-REGISTERED BAR (written before any backtest of this round; no goalpost moves)

- **Selection window ONLY**: run #231's saved `validate.windows.optimize` = **2010-06-07 →
  2025-02-10**, read from the Firestore run doc rather than assumed. The lockbox
  (`validate.windows.lockbox` = 2025-02-11 → 2026-08-12) is **SPENT**, confirmatory only, read
  once at the very end, and never used to rank a candidate.
- **Reproduction gate**: the harness must first reproduce, on the selection window, to the dollar
  and to the exact trade count — #231 champion 5,113 / $277,123.31 / DD $19,482.27 ·
  `skip_bot_short` 4,748 / $320,530 · `skip_bot_all` 3,991 / $308,783.01 / DD $15,933.92 ·
  `vol_skip` 90 4,309 / $310,689.59 · 95 4,697 / $302,963 · 98 4,868 / $309,055 ·
  `skip_bot_short`+`vol_skip 90` 4,054 / $320,130. Otherwise the study stops. **ALL 7 PASS.**
- **Rule 1 — Occam (carried from the campaign, unchanged)**: a combination must beat its BEST
  single component on BOTH net profit and net/DD (MAR), strictly.
- **Rule 2 — beat the standing champion** on net and MAR (implied by rule 1, stated anyway).
- **Rule 3 — PLATEAU (new, declared this round)**: declared neighbourhood is
  `daytype_lo` ∈ {0.15, 0.20, 0.25} × volatility threshold ∈ {90, 95, 98}. A winning cell must
  ALSO satisfy rule 1 at both of its immediate neighbours on the day-type axis and both on the
  volatility axis (edge cells: the one neighbour that exists). Clearing at exactly one setting is
  declared noise.
- **Rule 4 — era and worst-year guards (carried)**: 2010-17 net ≥ $0, worst calendar year not
  worse than the champion's (2010, −$2,278).
- **Rule 5 — CONCENTRATION, disqualifying**: report the best single year's share, the 10 best
  avoided trades' share, and years positive/negative. **DISQUALIFY if the improvement over the
  best single component goes to zero or negative once the 10 best avoided trades are removed.**
- **Rule 6 — OVERLAP, reported always**: for every promising pair, how many sessions both filters
  veto, how many only one vetoes, and what the champion's trades in each group were worth.
- **Cross-contract, reported not selected on**: ES sibling, nothing refitted, against **NOISE's own
  promotion bar of PF ≥ 1.2** — *not* the engine's generic cross-instrument sanity check of PF ≥ 1.0.

### VERDICT — nothing clears. Do not crown a combination.

| stage | what happened |
|---|---|
| Occam rule | 8 of 18 combination cells clear |
| Plateau | 5 of those 8 die; **3 survive**, all of them the NARROW filter at volatility 98 |
| **Concentration** | **all 3 survivors DISQUALIFIED** — 181%–320% of their improvement is 10 avoided trades |
| Net result | **0 of 18 cells clear the full pre-registered bar** |

**The broader day-type filter is the clearer failure.** Every `skip_bot_all` combination fails
either the Occam rule or the plateau rule. It clears Occam only at volatility 98 (at `lo` 0.15 and
0.20) and its neighbours fail in both directions, so it never plateaus. Against volatility 90 it is
actively destructive: `skip_bot_all` + `vol_skip 90` is **$287,858 / MAR 18.22**, which is $20,925
BELOW `skip_bot_all` alone and $22,832 below `vol_skip 90` alone.

### Selection-window grid (2010-06-07 → 2025-02-10), the cells that matter

| config | n | net $ | PF | MaxDD $ | net/DD (MAR) | 2010-17 $ | worst yr $ | Occam | plateau | concentration |
|---|---|---|---|---|---|---|---|---|---|---|
| #231 champion (baseline) | 5,113 | 277,123 | 1.241 | 19,482 | 14.22 | 11,524 | −2,278 | — | — | — |
| SBS lo0.20 (**run 241**) | 4,748 | 320,530 | 1.315 | 18,560 | 17.27 | 19,770 | −1,934 | single | — | banked broad |
| SBA lo0.20 (**run 245**) | 3,991 | 308,783 | 1.379 | 15,934 | 19.38 | 8,115 | −1,473 | single | — | banked |
| SBS + vs90 (**run 243**) | 4,054 | 320,130 | 1.420 | 18,425 | 17.38 | 19,303 | −1,934 | **fails** | — | — |
| vs90 alone | 4,309 | 310,690 | 1.375 | 19,041 | 16.32 | 17,967 | −2,278 | single | — | fragile (banked) |
| vs95 alone | 4,697 | 302,963 | 1.314 | 19,176 | 15.80 | 16,369 | −2,278 | single | — | fragile (banked) |
| vs98 alone | 4,868 | 309,055 | 1.304 | 19,176 | 16.12 | 18,560 | −2,278 | single | — | fragile (banked) |
| **SBS lo0.25 + vs98** | 4,470 | **330,978** | 1.368 | 18,560 | 17.83 | 21,511 | −1,934 | clears | PASS | **DISQUALIFIED** |
| **SBS lo0.20 + vs98** | 4,538 | 329,931 | 1.360 | 18,560 | 17.78 | 21,848 | −1,934 | clears | PASS | **DISQUALIFIED** |
| **SBS lo0.15 + vs98** | 4,608 | 323,997 | 1.345 | 18,826 | 17.21 | 19,821 | −2,065 | clears | PASS | **DISQUALIFIED** |
| SBA lo0.15 + vs98 | 4,085 | 328,165 | 1.408 | 17,622 | 18.62 | 13,668 | −1,630 | clears | FAIL | — |
| SBA lo0.20 + vs98 | 3,879 | 315,517 | 1.419 | 15,934 | 19.80 | 12,151 | −1,473 | clears | FAIL | — |
| SBA lo0.25 + vs98 | 3,638 | 306,710 | 1.437 | 13,618 | 22.52 | 10,021 | −1,635 | fails | — | — |
| SBA lo0.20 + vs95 | 3,818 | 295,441 | 1.402 | 15,934 | 18.54 | 8,480 | −1,483 | fails | — | — |
| SBA lo0.20 + vs90 | 3,556 | 287,858 | 1.438 | 15,798 | 18.22 | 12,748 | −1,473 | fails | — | — |
| SBS lo0.20 + vs95 | 4,402 | 322,345 | 1.368 | 18,560 | 17.37 | 16,573 | −1,934 | clears | FAIL | — |
| SBS lo0.20 + vs90 | 4,054 | 320,130 | 1.420 | 18,425 | 17.38 | 19,303 | −1,934 | fails | — | — |

The full 28-row grid (every `lo` × every threshold, plus both day-type modes alone) prints from
`python tools/noise_combo_study.py`.

**Note on run #243.** The variant the owner counts as one of the three is itself a combination —
skip-shorts stacked with the 10% volatility skip. Measured on the selection window it **fails the
Occam rule**: $320,130 is $400 BELOW skip-shorts alone. It passed validation, but it does not earn
its extra knob. That is the same −$400 the 2026-08-17 attribution already reported.

### OVERLAP — the crux, and it answers the question against the broader filter

Session-level veto sets on the selection window (3,770 sessions, day-type threshold 0.20). The
day-type filter fires on **665 sessions**; the volatility filter fires on 398 / 197 / 105 sessions
at thresholds 90 / 95 / 98. Champion trades and dollars are shown per bucket.

| vol threshold | day-type sessions | vol sessions | **BOTH** | day-type only | vol only | share of the vol filter's days already covered |
|---|---|---|---|---|---|---|
| 90 | 665 | 398 | **158** | 507 | 240 | **40%** |
| 95 | 665 | 197 | **94** | 571 | 103 | **48%** |
| 98 | 665 | 105 | **49** | 616 | 56 | **47%** |

| vol 90 bucket | champion trades | all-sides $ | shorts | shorts $ | **longs $ (derived)** |
|---|---|---|---|---|---|
| both veto | 369 | −54,491 | 109 | −33,379 | −21,112 |
| day-type only | 753 | +22,831 | 255 | −9,441 | **+32,272** |
| vol only | 435 | +20,925 | 160 | +27,372 | −6,447 |
| neither | 3,556 | +287,858 | 1,040 | +132,887 | +154,971 |

| vol 98 bucket | champion trades | all-sides $ | shorts | shorts $ | **longs $ (derived)** |
|---|---|---|---|---|---|
| both veto | 133 | −25,198 | 34 | −21,944 | −3,254 |
| day-type only | 989 | −6,462 | 330 | −20,875 | **+14,413** |
| vol only | 112 | −6,734 | 39 | +3,919 | −10,653 |
| neither | 3,879 | +315,517 | 1,161 | +156,340 | +159,177 |

**Read those two tables together and the whole round falls out of them.**

1. **The two filters do heavily veto the same days — 40% to 48% of the volatility filter's sessions
   are already weak-close sessions.** That is the overlap the campaign suspected, now measured at
   session level rather than inferred from headline dollars.
2. **The days they share are genuinely bad** — the champion loses $54,491 there at threshold 90.
   Both filters get credit for the same money. Stacking cannot bank it twice.
3. **The broader filter's extra reach is the problem, and it is a LONG problem.** On the 507
   sessions only the day-type filter vetoes, the champion's shorts lose $9,441 — correctly cut —
   but its LONGS make **+$32,272**. `skip_bot_short` keeps that. `skip_bot_all` throws it away.
   That single number is why the broader filter finishes $11,747 behind the narrower one on net,
   and why every combination built on it does worse still.
4. **So the answer to the crux question is that the broader filter overlaps the volatility skip
   MORE, not less.** It vetoes more sessions in total, it covers a slightly higher fraction of the
   volatility filter's days at every threshold, and the sessions it uniquely adds are ones where
   the strategy was making money on the long side. There is no complementary space for the
   volatility filter to fill.

### CONCENTRATION — what killed the three plateau survivors

Improvement measured against each survivor's own best single component (skip-shorts at the same
threshold), selection window.

| combination | Δ net $ vs best component | best year | its share | 10 best avoided trades | their share | **Δ ex those 10** | years +/− | verdict |
|---|---|---|---|---|---|---|---|---|
| SBS lo0.15 + vs98 | +13,775 | 2024 +7,656 | 56% | +24,948 | **181%** | **−11,174** | 10 / 2 | DISQUALIFIED |
| SBS lo0.20 + vs98 | +9,401 | 2024 +6,109 | 65% | +24,948 | **265%** | **−15,547** | 10 / 2 | DISQUALIFIED |
| SBS lo0.25 + vs98 | +7,785 | 2024 +6,109 | 78% | +24,948 | **320%** | **−17,163** | 10 / 2 | DISQUALIFIED |

The volatility leg contributes about 210 additional avoided trades. Ten of them are worth $24,948.
The other two hundred, taken together, LOSE between $11,174 and $17,163. The combination's entire
incremental value is a handful of days, which is exactly the fragility the 2026-08-17 round already
banked for the whole `vol_skip` family (83%–103% top-10 shares) and exactly what rule 5 exists to
catch. Nothing here is new evidence in the filter's favour; it is the same ten days arriving in a
different wrapper.

### CROSS-CONTRACT — ES sibling, nothing refitted, selection window

**Bar named explicitly: NOISE's own promotion bar is PF ≥ 1.2.** The engine's generic
cross-instrument sanity check is a looser PF ≥ 1.0, and the two have been confused before.
(The champion's row reproduces the campaign's banked ES probe exactly — 645.0 pts / PF 1.036.)

| config | ES trades | ES net pts | ES PF | ES MaxDD $ | ES MAR | PF ≥ 1.0 generic | **PF ≥ 1.2 NOISE bar** |
|---|---|---|---|---|---|---|---|
| SBS lo0.20 + vs98 | 4,664 | 1,561.5 | 1.113 | 19,196 | 4.07 | pass | **FAIL** |
| SBS lo0.25 + vs98 | 4,584 | 1,535.7 | 1.114 | 19,712 | 3.90 | pass | **FAIL** |
| SBS + vs90 (run 243) | 4,134 | 1,451.3 | **1.126** | 21,482 | 3.38 | pass | **FAIL** |
| SBS lo0.20 (run 241) | 4,900 | 1,424.4 | 1.093 | 24,217 | 2.94 | pass | **FAIL** |
| SBA lo0.20 + vs98 | 4,012 | 1,189.3 | 1.102 | 27,078 | 2.20 | pass | **FAIL** |
| SBA lo0.15 + vs98 | 4,271 | 1,149.3 | 1.091 | 28,736 | 2.00 | pass | **FAIL** |
| vs98 alone | 5,023 | 1,052.2 | 1.068 | 31,138 | 1.69 | pass | **FAIL** |
| SBA lo0.20 (run 245) | 4,171 | 1,018.1 | 1.079 | 33,869 | 1.50 | pass | **FAIL** |
| #231 champion | 5,312 | 645.0 | 1.036 | 41,480 | 0.78 | pass | **FAIL** |

- **Nothing clears NOISE's own PF ≥ 1.2 bar.** The best combination reaches 1.113, which is BELOW
  the already-existing run #243 at 1.126. No combination improves cross-contract transfer.
- The broader day-type filter transfers WORSE than the narrower one on ES as well (1.079 vs 1.093,
  1,018 pts vs 1,424 pts) — the same long-side amputation showing up on a second instrument.
- NOISE still has never cleared its own ES-transfer requirement. This round does not move that.

### CONFIRMATORY ONE-LOOK — read ONCE, after the decision, never used to select

Full window 2010-06-07 → 2026-08-12; the LB column is the continuous-run slice from 2025-02-11.
(The champion's $58,858 reproduces NOISE.md's banked continuous-slice figure exactly.)

| config | n | TOTAL net $ | PF | MaxDD $ | net/DD | LB n | LB slice $ |
|---|---|---|---|---|---|---|---|
| #231 champion | 5,633 | 335,981 | 1.221 | 32,794 | 10.25 | 520 | 58,858 |
| SBS lo0.20 (run 241) | 5,214 | 388,181 | 1.287 | 31,191 | 12.45 | 466 | 67,651 |
| SBA lo0.20 (run 245) | 4,404 | 366,855 | 1.337 | 29,041 | 12.63 | 413 | 58,072 |
| SBS + vs90 (run 243) | 4,429 | 380,745 | 1.387 | 22,096 | 17.23 | 375 | 60,615 |
| SBS lo0.20 + vs98 | 4,966 | 408,067 | 1.343 | 20,731 | 19.68 | 428 | 78,136 |
| SBS lo0.25 + vs98 | 4,874 | 406,400 | 1.350 | 21,605 | 18.81 | 404 | 75,422 |
| SBA lo0.20 + vs98 | 4,274 | 396,107 | 1.398 | 21,985 | 18.02 | 395 | 80,589 |

**⚠ THIS TABLE IS THE TRAP, AND IT IS RECORDED HERE SO THE NEXT SESSION DOES NOT FALL INTO IT.**
The disqualified combinations look like the best rows on the page — `SBS lo0.20 + vs98` posts the
highest total ($408,067), a MAR of 19.68 and the second-best lockbox slice, and `SBA lo0.20 + vs98`
posts the best lockbox slice of all ($80,589). **They were still rejected**, because the lockbox is
SPENT and the selection-window concentration test — declared before any of these numbers existed —
disqualified them. Promoting on this table would be selecting on the lockbox, which is precisely
the failure mode this project has caught and thrown out repeatedly. Anyone who wants to revive
`skip_bot_short` + `vol_skip 98` must do it on FORWARD data or a fresh instrument, with a new
pre-registration, not on these rows.

### RECOMMENDATION

1. **Crown no combination.** Zero of eighteen cells clear the pre-registered bar.
2. **The best answer remains a single variant: skip SHORT trades the day after a weak close
   (run #241).** It is the leg that carries the mechanism, it is the broad effect rather than a
   handful of days (55% top-10 share, +$19.3k still there after stripping its 10 best avoidances,
   positive in 13 of 16 selection-window years), it improves ES transfer most in points among the
   validated singles, and it is the only one of the three whose extra knob count is minimal.
3. **The broader filter (run #245) is NOT the better single**, despite its stronger lockbox. On the
   selection window it is $11,747 behind on net, it transfers worse to ES, and the overlap table
   above says exactly what it is giving up: $32,272 of profitable long trades on weak-close days.
   Its better drawdown and MAR are real, so it stays a legitimate risk-reduction alternative if the
   owner ever wants smaller drawdowns at lower net — but it is not the crown.
4. **Run #243 should not be treated as a third independent variant.** It is skip-shorts with a
   volatility skip stacked on top, and that stack fails the Occam rule by $400 on the selection
   window. If it is kept, keep it knowing the extra knob is not paying for itself.
5. **The `vol_skip` family stays a banked single and should not be stacked on anything.** Three
   independent rounds have now reached that conclusion by three different routes.

**Nothing was queued.** No candidate cleared, so no pinned strategy file was built, no
execution-feasibility audit was needed, and no auto-validate job was created. The job queue was
left untouched, the runner was not restarted, and no data master was imported or refreshed.


---

## Still genuinely untested (not dead ends — nobody has run these)

- ~~Combining the validated variants into an "ultimate crown"~~ — RUN 2026-08-21 (see the
  "2026-08-21 — combination study" section): 18 combination cells over both day-type modes x
  3 weak-close thresholds x 3 volatility thresholds. **Clean negative — nothing clears the
  pre-registered bar.** The broader day-type filter (`skip_bot_all`) overlaps the volatility
  skip MORE than the narrower one does (40-48% of the volatility filter's days are already
  weak-close days) and its extra reach throws away $32,272 of profitable LONG trades. Do not
  re-propose a NOISE filter stack without new forward data and a fresh pre-registration.
- **NOISE in a BOOK job.** BOOK (pool N legs, score as ONE strategy) exists since v71.42
  and has never had NOISE put through it. NOISE↔ORB correlation measured **0.21–0.25**
  (twice, rounds 10 and 12) — low enough to expect real diversification — but no blended
  backtest was ever actually run.
- ~~TRADE CONTEXT feature→PnL FDR scan on NOISE~~ — RUN 2026-08-18 (see the section above):
  96 tests over 16 features x 2 configs x 3 sides. The scan works — it rediscovers the known
  day-type effect blind on the champion's shorts and watches it vanish under `skip_bot_short`
  — but **nothing survived correction that is not already explained** by the banked volatility
  and weak-close mechanisms. `gap_pct` was the one new-looking lead and 78% of it sits inside
  `vol_skip 90` already. No new knob recommended.
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

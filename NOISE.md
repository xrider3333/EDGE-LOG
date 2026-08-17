# NOISE — wide-band intraday momentum envelope: lockbox findings & open questions

> Living handoff doc. **Last updated: 2026-08-17** (variant campaign session — see the
> "2026-08-17 — variant campaign" section: pre-registered entry-quality filters cleared
> the bar; knobs shipped in `NOISE_1_0.py`; controlled auto-validate queued).
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
> 12 cells incl. the exact champion cell, for a controlled auto-validate comparison.

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
met. The queued auto-validate (below) is the owner-visible arbiter (fresh WF machinery on
the controlled 12-cell preset).

**Known-unknown flagged:** run #225/#231's headline n/net (e.g. 3,872 / $96,611) don't
match the raw-engine path on the same source/params (5,113 / $277,123 on the shorter
selection window; harness == `augur_engine.engine.run_backtest` exact) — the validate
pipeline's champion-metrics convention differs from the raw engine path. Run-to-run
comparisons inside the runner remain apples-to-apples; worth a separate reconciliation.

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

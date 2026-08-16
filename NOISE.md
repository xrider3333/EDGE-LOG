# NOISE — wide-band intraday momentum envelope: lockbox findings & open questions

> Living handoff doc. **Last updated: 2026-08-15** (Claude Code, PAPER/NT-bridge session).
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
3. **ES-transfer needs reconciling.** #225 records transfer **PASS at PF 1.033**
   (`validate.transfer`: ES, 5,796 trades, pnl 709.51). But `NOISE_1_0.py`'s docstring
   calls ES-transfer a **FAIL at PF 1.12** — a *higher* PF. Either the threshold moved,
   or the two are measuring different things. ES-transfer is load-bearing for crowning,
   so this should be settled before it's leaned on either way.
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

## Still genuinely untested (not dead ends — nobody has run these)

- **Vol-regime filter / vol-conditional exit.** Named in `NOISE_1_0.py`'s docstring as
  "the natural next lever," never built. The lead is concrete: 2020 vwap-exits −$91.7k
  vs EOD-flats +$84.1k (round-12 autopsy, `BACKTESTING_STACK.md` ~584). An `atr_filter`
  exists in the ORB family and has never been ported to NOISE.
- **NOISE in a BOOK job.** BOOK (pool N legs, score as ONE strategy) exists since v71.42
  and has never had NOISE put through it. NOISE↔ORB correlation measured **0.21–0.25**
  (twice, rounds 10 and 12) — low enough to expect real diversification — but no blended
  backtest was ever actually run.
- **TRADE CONTEXT feature→PnL FDR scan on NOISE.** The engine (`augur_engine/context.py`)
  is generic and wired in; no NOISE-specific scan is recorded anywhere.

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

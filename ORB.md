# ORB — Opening Range Breakout: status, results & backlog

> Living handoff doc. **Last updated: 2026-07-03** (Claude Code).
> Sibling of `ROADMAP.md`. Purpose: any human or Claude can pick ORB up cold from here.
> All $ are **net of fees** unless flagged. Fees: commission $5.66 + slippage 0.25pt →
> `cost_pts` = **0.533 (NQ, mult 20)**, **0.363 (ES, mult 50)**. Data: `NOADJ_NQ_5m_RTH.csv`
> (316,983 bars · 4,126 sessions · 2010-06-07 → 2026-06-30). Lockbox = last 365 days
> (2025-06-30 → 2026-06-30), never seen during selection. **MAR = net PnL ÷ |max drawdown|.**

---

## 0. TL;DR — where we stand

- **Deployable config is settled and triple-validated** (walk-forward, lockbox, ES transfer):
  **single lot · OR=1 · Both · stop 0.75 · vol 1.25 · ride-to-close · flat EOD · 5-bar trailing stop.**
  = `ORB_3_1.py` at `partial_exit_R=0, trail_bars=5`. Saved as **run #125** (starred).
- **The trailing stop is the whole game.** It halves drawdown (−$26k → −$9k) and doubles MAR
  (15 → 33) vs no trail, for ~25% less gross PnL — which you *make back and more* by sizing up.
- **The 2-lot "book early" partial is optional** — it lifts win-rate (→50-60%) but not MAR. Psychology lever, not an edge lever.
- **Smarter trails were tested and lost:** chandelier ATR trail overfits (great in-sample, worse on lockbox); activation hurts; breakeven@1R is a wash. Simple fixed bar-trail wins forward.
- **Edge is structural:** the NQ config transfers to ES with no re-fit (ES lockbox PF 1.57).
- **Vol-target (risk-parity) sizing is a modest but GENERALIZING win** (unlike the chandelier):
  size ∝ 1/initial-risk lifts lockbox MAR +29% (6.9 → 8.9) and roughly halves drawdown, at the
  cost of absolute PnL at equal average size (you recover it by sizing up into the freed DD budget).
  Best practical form: **risk-parity capped at 3× avg size (`rp-cap3`)**, applied at the execution layer.
- **ML gate does NOT earn its keep on ORB** (per ROADMAP #25) — ORB is already clean/high-volume. Keep the gate for marginal strategies (VWAP FADE), not ORB.

- **Best result — the sizing overlay (§4.7/4.10/4.11):** THREE independent edges *stack* into one
  execution-layer size rule — **risk-parity** (∝1/stop) **× time-tilt** (~2× the morning PF window)
  **× short-tilt** (shorts carry the edge; longs are ~deadweight, PF 1.03 vs 2.74, confirmed on ES).
  Capital-matched, the full stack lifts lockbox MAR **6.9 → 15.0 (+118%)**, PF 1.63 → 2.85, winning
  5/6 WF folds. No entry/exit change (§5.6 deploy rule). *Tilt, don't cut* — truncation/short-only balloon DD.
- Consolidated into reusable code (item F): `augur_engine/sizing.py` + `tools/orb_edge_report.py`.

**Next up: the edge-hunting is done. Ship it — wire the sizing overlay + MAR column into the app (owner-reviewed, changes core PnL semantics), or deploy as-is.** *(E: ride+trailed ensemble = minor smoothing.)*
*(Tested & rejected: smarter trailing (chandelier/activate/breakeven), regime skip `atr_filter`, midday time-stop, morning-only truncation — the trail already handles low-vol/stalled trades; truncation balloons drawdown.)*

---

## 1. Deployable config (current best)

| param | value | why |
|---|---|---|
| `or_bars` | 1 | WF-preferred; 5-min opening range |
| `trade_mode` | Both | two-sided |
| `stop_frac` | 0.75 | validated; **0.5 is a hard floor** (below it PF is a fill artifact) |
| `vol_filter` | 1.25 | skip thin-volume fake pokes |
| `breakout_buf` | 0.0 | trade the touch |
| `target_R` | 0.0 | ride to session close (no fixed cap) |
| `flat_eod` | True | no overnight gap risk |
| `partial_exit_R` | 0.0 | OFF (optional — set 1.5-2.0 only if you want higher win-rate) |
| `trail_bars` | **5** | the risk-adjusted lever — trails the N-bar low/high |

**Measured (full history 2010→2026, net):** $360,640 · WR 41% · PF 1.61 · maxDD −$9,352 · **MAR 38.6**.

---

## 2. Strategy file lineage

| file | what it is | status |
|---|---|---|
| `ORB_1_0.py` | v1 — bare breakout, ride to EOD | superseded |
| `ORB_2_0.py` | v2 — full-featured: ATR stop + partial + bar-trail + vol filter | source of levers |
| `ORB_3_0.py` | **v3 low-DOF deployable** — 5 knobs, no partial/trail (clean WF surface) | base |
| `ORB_3_1.py` | v3 base **+ partial_exit_R + trail_bars** (2-lot scale-out) | **DEPLOYABLE** |
| `ORB_3_2.py` | research fork — chandelier ATR trail + activate + breakeven | research only (invariant-verified == 3.1 when levers off) |

---

## 3. Run ledger (post-prune, ORB family = 13 runs)

Pruned 2026-07-03: removed 4 exact-duplicate re-runs + 3 superseded ETH runs (backup
`optimizer_history.db.bak_20260703_163836_preprune`). Kept:

| id | strategy | source | net $ | WR | PF | maxDD | note |
|---|---|---|---|---|---|---|---|
| 105 | ORB v2 | NQ ETH | $214k | 11% | — | −$35k | kept as the "ETH doesn't work" record |
| 111 | ORB v2 | NQ RTH | $352k | 52% | 1.17 | −$78k | high-DD config |
| 112 ★ | ORB v2 | NQ RTH | $410k | 45% | 1.50 | −$18k | v2 deployable keeper |
| 115-116 | ORB v2 | NQ RTH | $531-619k | 46-54% | 1.3 | −$42-79k | |
| 117 ★ | ORB v2 | NQ RTH | $547k | 55% | 1.49 | −$42k | |
| 118 | ORB v2 | ES RTH | $305k | 40% | 1.44 | −$12k | ES |
| 119 | ORB 3.0 | NQ RTH | $134k | 39% | 1.69 | −$5.8k | SAFE base (0.75/4.5R/holds o-n) |
| 120 | ORB 3.0 | ES RTH | $314k | 39% | 2.51 | −$4k | |
| 121 | ORB 3.0 | NQ RTH | $615k | 20% | 2.50 | −$10k | AGGRO — **0.25 stop below floor, PF inflated** |
| 122-124 | ORB 3.0 | NQ/ES | $251-518k | 43-51% | 1.3-1.4 | −$16-63k | |
| 125 ★ | **ORB 3.1** | NQ RTH | $361k | 41% | 1.61 | −$9.4k | **deployable, WF+lockbox+ES validated** |

---

## 4. Results (measured)

### 4.1 The original question — 119 (safe) vs 121 (aggressive)
Same strategy, different knobs. 119 = 0.75 stop / 4.5R cap / holds overnight → smooth, small.
121 = 0.25 stop / ride-to-close / flat EOD → big PnL but **0.25 is below the 0.5 floor, so its
$615k/PF2.50 was partly a fill artifact.** A safe 0.75 stop with ride-to-close still nets ~$407k
→ the underlying edge is real; the tight stop inflated it.

### 4.2 Exit-lever frontier (full pre-lockbox sweep, MAR-ranked)
The single-lot no-trail config wins on **PnL**; a trail wins on **risk-adjusted return**:

| partial / trail | net $ | WR | PF | maxDD | MAR |
|---|---|---|---|---|---|
| p0 / **t5** | $307k | 41% | 1.61 | −$9.4k | **32.8** ← risk-adj champ |
| p0 / t8 | $310k | 37% | 1.59 | −$9.6k | 32.2 |
| p3.0 / t5 | $348k | 44% | 1.44 | −$15.9k | 21.9 |
| p2.0 / t0 | $354k | 50% | 1.50 | −$22.3k | 15.9 |
| p0 / t0 (single lot) | **$407k** | 38% | 1.49 | −$26.4k | 15.4 ← PnL champ |

Trail (t3/t5/t8) tops the MAR frontier → it's a **plateau, not a spike** (robust). Partial only raises WR.

### 4.3 Walk-forward (expanding window, 6 folds, pre-lockbox)
- PnL-ranked: **6/6 folds OOS-positive**, OOS total $391k. Per-fold champ mostly single-lot.
- MAR-ranked: **6/6 folds OOS-positive**, OOS total $287k. Per-fold champ mostly p0 + trail.

### 4.4 Lockbox one-shot (unseen last 12 mo) — **PASS**
| config | net $ | WR | PF | maxDD | MAR |
|---|---|---|---|---|---|
| p0/t0 (PnL champ) | $84.6k | 40% | 1.59 | −$17.1k | 4.96 |
| **p0/t5 (deployable)** | $54.1k | 40% | **1.63** | −$7.9k | **6.88** |

### 4.5 Trailing research (ORB 3.2) — smarter trail LOSES to simple
| variant | in-sample MAR | lockbox PF | verdict |
|---|---|---|---|
| bar-trail 5 (baseline) | 32.8 | **1.63** | robust winner |
| chandelier 0.15×ATR | **38.9** (best in-sample) | 1.45 | **OVERFIT** — worse OOS |
| bar-trail 5 + breakeven@1R | 34.1 | — | mild in-sample only |
| bar-trail 5 + activate@1R | worse DD | — | hurts (give-back) |

*(Chandelier is scaled in session-range units, so multipliers are small ~0.15, not the 2.5-4 a bar-ATR chandelier uses.)*

### 4.6 ES transfer (NQ config, no re-fit) — **PASS**
| window | net $ | WR | PF | maxDD | MAR |
|---|---|---|---|---|---|
| ES full | $186.7k | 39% | 1.47 | −$7.4k | 25.4 |
| ES lockbox (unseen) | $26.7k | 33% | **1.57** | −$5.4k | 4.97 |

Edge holds on a sibling instrument it was never fit to → **structural**, not an NQ artifact.

### 4.7 Vol-target (risk-parity) sizing — modest, and it GENERALIZES ✅
Re-weight position size ∝ 1/initial-risk (constant-$ risk per trade) vs fixed 1 contract,
capital-matched (mean size = 1), fee scales with size. `rp-cap3` = risk-parity capped at 3× avg;
`rp-sqrt` = dampened (size ∝ 1/√risk).

| window | scheme | net $ | PF | maxDD | MAR |
|---|---|---|---|---|---|
| full | fixed (baseline) | $360.6k | 1.61 | −$9.35k | 38.6 |
| full | rp-cap3 | $188.8k | 1.73 | −$4.26k | 44.3 |
| full | rp-sqrt | $255.9k | 1.67 | −$5.02k | **50.9** |
| **lockbox** | fixed | $54.1k | 1.63 | −$7.87k | 6.88 |
| **lockbox** | **rp-cap3** | $55.2k | 1.72 | −$6.24k | **8.85** (+29%) |

- Improves MAR on full history (38.6 → 44-51), the unseen lockbox (6.9 → 8.9), and **4 of 6 WF folds**.
  Cuts drawdown ~in half; lifts PF (1.61 → 1.73). **Survives the lockbox** — a real edge, not a mirage.
- Costs absolute PnL *at equal average size* because it downsizes the wide-OR trend days that make the
  fat tail. On a **drawdown budget** (size up to the old DD) rp-sqrt ≈ **+32% return** at equal risk.
- Best practical: **`rp-cap3`**. It's a sizing OVERLAY at the execution layer (contracts per signal),
  not a signal change — see the deploy rule in §5.6 below.
- Caveats: realize it via whole-contract rounding (cleaner on micros/larger accounts); risk-parity
  concentrates size into quiet-day tight-stop trades (the cap + the 1.25 vol filter mitigate the tail).

### 4.8 Regime skip (`atr_filter`) — NO help on the trailed base ✗
Sweep of `atr_filter` (skip a session whose recent 5-session avg range < x × trailing-60 median),
deployable p0/trail5, pre-lockbox, net:

| atr_filter | trades | net $ | PF | maxDD | MAR |
|---|---|---|---|---|---|
| **0.0 (off)** | 3,814 | $306.5k | 1.61 | −$9.35k | **32.8** |
| 0.6 | 3,713 | $294.1k | 1.59 | −$9.35k | 31.5 |
| 0.8 | 3,120 | $232.9k | 1.54 | −$12.46k | 18.7 |
| 1.0 | 2,116 | $142.0k | 1.46 | −$11.31k | 12.6 |

- **Every filter > 0 lowers MAR, PF, and net $; drawdown doesn't improve (gets *worse* at 0.8+).**
  Best value is OFF. Same verdict on lockbox + 0/6 WF folds (best filter = 0.0, so identical to baseline).
- **Why:** the regime report flagged low-vol days as ORB's bleeding bucket on an **untrailed** config.
  The 5-bar trailing stop already exits the quiet-day chop fast, so those days aren't bleeding anymore —
  skipping them just removes trades (some are winners) and *concentrates* the remaining drawdown.
  **Regime-skip and the trail are substitutes, not complements.** Leave `atr_filter = 0`.

### 4.9 Time structure — time-stop ✗, but entry-time reveals a real edge signal ◐
Two session-clock levers (`ORB_3_3.py`, 5m RTH: bar t ≈ 9:30 + 5·t min), net of fees:

**Midday time-stop (force-exit at session-bar X) — REJECTED.** Every setting worsens it:
| time_stop_bar | net $ | PF | maxDD | MAR |
|---|---|---|---|---|
| 0 (off) | $306.5k | 1.61 | −$9.35k | 32.8 |
| 48 (~13:30) | $260.5k | 1.54 | −$13.7k | 19.0 |
Same story as regime-skip: the trailing stop already exits stalled trades; a hard time-exit just cuts winners.

**Entry-time cutoff (only enter before session-bar X) — a real QUALITY signal that generalizes:**
| cutoff | window | trades | net $ | PF | maxDD | MAR |
|---|---|---|---|---|---|---|
| 0 (all day) | — | 3,814 | $306.5k | 1.61 | −$9.35k | **32.8** |
| 6 | first 30 min | 438 | $56.6k | **2.45** | −$4.65k | 12.2 |
| 12 | **first hour** | 1,185 | $158.5k | **2.20** | −$6.42k | 24.7 |
| 36 | first 3 h | 2,189 | $248.6k | 1.99 | −$10.2k | 24.5 |

- **The morning breakouts carry the edge** — PF rises monotonically the earlier you cut off (first-hour
  PF 2.20 vs all-day 1.61). On the unseen **lockbox, cutoff-12 PF = 3.48 vs 1.63**, and it has higher PF
  in **6/6 WF folds**. The quality signal is real and robust.
- **But it's quality-vs-quantity:** fewer trades → less total $ → *naive* MAR favors trading all day
  (32.8 > 24.7). So "just stop trading at 1pm" is NOT a drop-in win.
- **The payoff is edge-concentration, not truncation:** trade first-hour-only and **size up** (the higher
  PF supports more risk/trade), or tier size by time-of-day. Paired with §4.7 sizing this could match the
  all-day $ at lower drawdown, far fewer trades, less fee/slippage drag. → **backlog item G.**

### 4.10 Entry-time × sizing (item G) — the combo WINS ✅ *(best result of the study)*
Capital-matched to the **same total $risk budget** (a fair "where do you spend the risk?" test).
Tier weights (morning ×2 / midday ×1 / afternoon ×0.5) are a **fixed a-priori rule** → lockbox is clean OOS.

| scheme (capital-matched) | full MAR | lockbox MAR | full PF | lockbox PF |
|---|---|---|---|---|
| baseline all-day, size 1 | 38.6 | 6.88 | 1.61 | 1.63 |
| risk-parity alone (A) | 44.3 | 8.85 | 1.73 | 1.72 |
| time-tiered alone | 38.8 | 10.52 | 1.89 | 2.08 |
| morning-only truncation | 29.7 | 7.67 | 2.31 | 3.48 |
| **time-tiered × risk-parity (the combo)** | **48.1** | **12.74** | **2.02** | **2.16** |

- **The two edges stack.** Time-of-day tilt and risk-parity are independent; combined MAR (48.1 full,
  **12.74 lockbox = +85% vs baseline**) beats either alone. Combo MAR > baseline in **5/6 WF folds**,
  higher PF in all 6. Best risk-adjusted result in the whole ORB study.
- **Truncation is the wrong way to use the morning edge** — morning-only MAR (29.7) is *below* baseline:
  concentrating the whole risk budget into 31% of trades balloons drawdown. **Keep all trades, tilt size.**
- **Deploy = execution-layer overlay** (no entry/exit change): `size ∝ time_weight(entry_hour) ×
  cap3(1/stop_dist)`, then hard-cap the final size (§5.6). Raw combo maxSz ~14× → cap it for realism.
- Honest caveats: the tier weights are deliberately **un-tuned** (a-priori) to avoid overfit — surviving
  the lockbox un-tuned is the signal; a fitted weight curve would need its own WF. The `WR` on morning-only
  rows is a display artifact (zeroed afternoon trades dilute it) — read PF/MAR, not WR, there.

### 4.11 Long/short asymmetry (item D) — shorts carry the edge ✅ *(2nd-biggest finding)*
Split the deployable's trades by side (net of fees, size 1):

| side | trades | net $ | PF | MAR |
|---|---|---|---|---|
| **LONG only** | 2,199 | $11.8k | **1.03** | 0.30 |
| **SHORT only** | 1,865 | $348.9k | **2.74** | 41.2 |

- **The longs are ~deadweight; the shorts are the whole edge.** Holds on the lockbox (SHORT PF 2.71 vs
  LONG 1.04) and **transfers to ES** (SHORT PF 2.18 vs LONG 1.09) → structural index-futures behaviour,
  not an NQ artifact. Plausible mechanism: indices gap up overnight, so the intraday *long* break of the
  tiny opening range buys the post-gap high and gets faded; *short* breaks catch the sharp risk-off moves.
- Stacks with everything (capital-matched):

| scheme | full MAR | lockbox MAR | lockbox PF |
|---|---|---|---|
| baseline | 38.6 | 6.88 | 1.63 |
| + short-tilt L0.5/S1.5 (alone) | 53.6 | 8.10 | 2.08 |
| G combo (time × rp) | 48.0 | 12.74 | 2.16 |
| **G combo + short-tilt (full deploy stack)** | **71.5** | **15.00** | 2.85 |
| full stack, short-**only** | 82.4 | 11.64 | **3.80** |

- **Short-*tilt* beats short-*only* on MAR** (a little long diversifies the drawdown) — same "tilt, don't cut"
  lesson as truncation. Full deploy stack: **lockbox MAR 15.0 = +118% vs baseline**, PF 2.85; 5/6 WF folds beat baseline.
- **The whole stack transfers to ES** (no re-fit, `python tools/orb_edge_report.py ES`): ES lockbox
  MAR **5.0 → 13.5 (+170%)**, PF 1.57 → 3.10, each lever adding monotonically (short-only ES lockbox PF 4.99).
  The short-tilt is the dominant lever on both instruments → the overlay is structural, not an NQ fit.
- **Caveats (deploy short-tilt, not hard short-only):** this is a 2010-2026 *secular-bull* sample; short
  books carry squeeze / gap-up tail risk; the short *direction* was chosen after seeing the split (though
  it's stark, OOS-confirmed, and cross-instrument). A regime flip could revive longs / punish shorts —
  size the tilt, keep some long, and re-check per regime.

---

## 5. What a pro would actually do here (principles)

1. **Size on drawdown, not PnL.** Fixed max-DD risk budget → at −$9k DD you carry ~2.8× the
   contracts you could at −$26k. 2.8 × $307k ≈ **$860k** vs the single-lot's $407k. The
   "lower-PnL" trailed config is really the ~2× *higher*-earning one at equal risk.
   **Headline PnL is a trap; MAR/Calmar is the currency.**
2. **Decompose levers; keep only what pays.** We split trail vs partial; trail carries the water.
   Drop the partial from deploy (no MAR gain, more complexity). Occam.
3. **Demand a plateau, not a spike.** t3/t5/t8 all score MAR 27-33 → robust, not curve-fit.
4. **Trust the lockbox over the in-sample number.** The chandelier's prettier in-sample MAR was
   a mirage; the reserved slice is the only honest judge.
5. **Rank deploy decisions by MAR in the app.** The runs table already stores `best_dd_usd`; a
   MAR column / `rank_by="mar"` is a trivial, high-value add (would've surfaced this on sweep #1).
6. **Size each signal by its stop, its entry hour, AND its side (§4.7 + §4.10 + §4.11 deploy rule).**
   `contracts = round( T · S · RISK_$ / (0.75 × OR_width_pts × $per_pt) )`, clamped to `[1, 3× baseline]`,
   where **RISK_$** = fixed per-trade dollar risk (~0.5-1% equity), **T** = time-of-day tilt (≈2× first-hour,
   1× midday, 0.5× afternoon), **S** = side tilt (≈1.5× short, 0.5× long — shorts carry the edge). Tight-stop
   / morning / short signals get more contracts. Three **independent** edges that stack → **lockbox MAR 6.9 → 15.0**.
   Execution-layer only; entries/exits unchanged. Implemented in `augur_engine/sizing.py`; reproduce with
   `python tools/orb_edge_report.py`.

---

## 6. Backlog — investigation TODO (by expected payoff)

| # | idea | expected payoff | status | result |
|---|---|---|---|---|
| E | **Ensemble** — 1 lot full-ride + 1 lot trailed → blended curve between MAR 15 and 33 (your original 2-contract idea, done right) | MED (smoothing, not new edge) | ☐ TODO | — |
| — | Smarter trailing (chandelier / activate / breakeven) | — | ☑ DONE | chandelier overfits; activate hurts; breakeven wash. **Simple bar-trail wins.** |
| A | **Vol-target (risk-parity) sizing** | HIGH | ☑ DONE | **WIN (modest, generalizes)** — lockbox MAR +29% (6.9→8.9), DD ~halved, PF→1.73, survives lockbox + 4/6 WF folds. Best = `rp-cap3` overlay (§4.7, deploy rule §5.6). |
| B | **Regime skip** (`atr_filter`) | MED-HIGH | ☑ DONE | **NO help** (§4.8) — every filter>0 lowers MAR/PF/PnL, DD doesn't improve. The trail already neutralizes low-vol days (substitutes, not complements). Leave off. |
| C | **Time structure** (`ORB_3_3.py`) | MED | ☑ DONE | time-stop ✗ (cuts winners); **entry-time cutoff = real quality signal** (first-hour PF 2.2, lockbox 3.5, 6/6 WF folds) but quality-vs-quantity on raw MAR → spawned item **G** (§4.9). |
| **G** | **Entry-time × sizing combo** | HIGH | ☑ DONE | **WIN** (§4.10). Time-tilt × risk-parity *stack*: lockbox MAR +85% (6.9→12.7), 5/6 WF folds. Truncation ✗ — tilt, don't cut. |
| **D** | **Long/short asymmetry** | MED | ☑ DONE | **WIN — shorts carry the edge** (§4.11). LONG PF 1.03 (deadweight) vs SHORT PF 2.74; holds on lockbox + ES. Short-tilt stacks → full stack lockbox MAR **15.0 (+118%)**, PF 2.85. Deploy short-tilt not short-only. |
| **F** | **Consolidate — durable code + MAR in the app** | HIGH leverage | ☑ DONE | `augur_engine/sizing.py` (rp × time × side overlay, capital-matched, MAR helper); `tools/orb_edge_report.py` (reproduces §4 numbers exactly); `run_grid(rank_by="mar")` (committed); `history.py` returns a derived `mar` field; **MAR column shipped to the web app (v44.5)** — champion cards, COMPARE + RANKINGS tables. *Phase 2 (open):* a sizing-overlay toggle in the web needs a sized-backtest runner job (changes core PnL semantics → owner-reviewed). |
| — | ES transfer (base config + long/short + full sizing stack) | — | ☑ DONE | **PASS all three** — base ES lockbox PF 1.57; long/short asymmetry transfers; **full sizing stack transfers** (ES lockbox MAR 5.0→13.5 = +170%, PF→3.10). |
| — | Walk-forward + lockbox of the scale-out | — | ☑ DONE | **PASS** (6/6 folds, lockbox PF 1.63) |

**Recommended next:** the edge-hunting is done and the wins are shipped where safe — deployable +
3-lever sizing overlay (rp × time × short-tilt) lift lockbox MAR **6.9 → 15.0** (all validated, ES-confirmed),
and the **MAR column is live in the app (v44.5)**. The only substantial item left is **phase-2: a
sizing-overlay toggle in the web** (a sized-backtest runner job — owner-reviewed, alters core PnL
semantics). Everything else is minor (E: ride+trailed ensemble). Otherwise: **deploy the §5.6 rule.**

---

## 7. Methodology & reproduction notes

- **Engine, headless (no Streamlit):** `augur_engine.optimize.run_grid` (constrained grid sweep,
  `grid={param:[...]}`, `date_from/date_to` windowing, `cost_pts`, `rank_by`), and
  `augur_engine.engine.run_backtest` (single config). Both match the app's math (`_apply_costs`).
- **Data:** `find_master("NQ","5m","rth")` → `NOADJ_NQ_5m_RTH.csv`. ES via `"ES"`.
- **Scale-out accounting (3.1/3.2):** a scaled-out session books **one blended trade** = `partial*0.5
  + runner*0.5`, so `num_trades`/`win_rate` stay comparable to single-lot runs and v2 history.
- **Invariant guarantee (3.2):** with `trail_atr=0, trail_activate_R=0, breakeven_R=0` the file is
  byte-equivalent to 3.1 — asserted in the `__main__` smoke test (`python augur_strategies/ORB_3_2.py`).
- **Walk-forward:** expanding window, 6 folds over the pre-lockbox span; per fold optimize the grid on
  all prior data, test the champion OOS; then one lockbox look for the full-span champion.
- **Durable artifacts (item F):** `augur_engine/sizing.py` = the sizing overlays (risk-parity × time-tilt ×
  side-tilt, capital-matched) + `trade_features()` (recompute per-trade risk/entry-bar/side from engine
  trades) + `mar()`. `tools/orb_edge_report.py [NQ|ES]` reproduces the §4 edge-stack tables exactly.
  `run_grid(rank_by="mar")` ranks by drawdown-adjusted return (verified; commit pending shared-file coord).
- *(The exploratory WF/rerank scripts ran from the session scratchpad and are ephemeral — this doc, the
  engine calls above, and the `tools/` report are the durable record.)*

---

## 8. Lessons / caveats (rap sheet)

- **0.5 stop floor is real** — sub-0.5 stops inflate PF via the exact-stop-fill assumption
  (stop 0.1 → fake PF 4.5). Run 121's 0.25 stop is why its numbers looked too good.
- **Gap-through realism is on** — stop fills at the bar open when it gaps through, not at the stop price.
- **ETH is not tradeable for ORB** — WR 9-11%, DD −$35k to −$155k (runs 105-110). RTH only.
- **Half-day / holiday sessions are low quality** — `skip_holidays` detects them by bar count.
- **Low-vol days are ORB's bleeding bucket** — motivates backlog item B (`atr_filter`).
- **Rank by MAR, not PnL** — PnL ranking wrongly crowned the single-lot no-trail config; every
  risk-adjusted lens (PF, MAR, lockbox) prefers the trailed one.
- **In-sample ≠ deployable** — the chandelier proved it. Always let the lockbox decide.

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

### 4.12 Auto-Validate vs the deployable — the PF objective goes short-only (2026-07-09)
Reconciliation ask: compare 3.0 (137) vs 3.1 side-by-side, all auto-validated the same way. Two findings:

**(a) Auto-Validate on `ORB_3_1.py` does NOT reproduce 125 (run #150).** Same pipeline as 137 (NQ 5m RTH
no-adj, cost 0.533, discover=auto, 300 trials, 12mo lockbox). It PASSED but discovered a **short-only**
champion — `or1/stop1.75/trail6/target4.0R/partial1.5/atr0.6` — because Auto-Validate ranks by PF/robustness,
so it re-finds the §4.11 short edge and drops the near-break-even longs. *"Auto-validate the strategy" ≠
"validate 125"; to stamp the deployable you must PIN its params* — see `augur_strategies/ORB_3_1_125.py`
(deploy-lock: search space collapsed to the single 125 config → run #~151).

**(b) 4-way head-to-head** — each config's EXACT params on identical no-adj data (cost 0.533, full 2010–2026;
ALL 6/6 folds net-positive + lockbox-positive → *none overfit*), `tools/…/compare_configs.py`:

| config | net $ | max DD | PF | trades | **MAR** | LB PF |
|---|--:|--:|--:|--:|--:|--:|
| 136 · 3.0 grid argmax (or3/stop.75/ride, Both) | $561k | $26.5k | 1.40 | 4,060 | 21.1 | 1.29 |
| 137 · 3.0 auto-validate (or1/stop1.75/4.5R, Both) | **$567k** | $40.2k | 1.47 | 3,951 | 14.1 | 1.51 |
| **125 · 3.1 deployable** (or1/stop.75/trail5, Both) | $361k | **$9.4k** | 1.61 | 4,064 | **38.6** | 1.63 |
| 150 · 3.1 auto-validate (**short-only**) | $385k | $27.9k | 1.57 | 2,291 | 13.8 | **1.70** |

- **125 stays the risk-adjusted king** (MAR 38.6, DD $9.4k) — the trail's DD magic only appears in the
  Both / tight-stop / ride+trail form; the PF-maximizing search never reaches it.
- **137** = highest PnL + best "Both" lockbox, at 4× 125's drawdown. **136** is genuinely robust, just
  Pareto-dominated (137 on PF/lockbox, 125 on DD) → fine to keep archived. **150 short-only** has the best
  *recent* edge (LB PF 1.70) but 3× 125's DD — a research signal (§4.11), not the deployable.
- **Lever if you don't want short-only:** pin `trade_mode=Both`, or rank discovery by **MAR not PF**
  (why MAR-ranked 125 stays two-sided). Runs 126–133/135 archived (dups of 137 / dominated).

### 4.13 Anatomy of 137's −$40k drawdown + breakeven finding (2026-07-09)
137's max DD (−$40,233) is **Apr 9 → Jul 11 2025**: the tariff-shock crash + V-recovery (NQ 17,276 → low
17,202 → 22,955, +33%). 62 trades / 40 losers. **No session-time or direction filter dodges it — they
INVERT it:** open-hour trades lost −$21.6k (vs the usual morning edge), shorts lost −$21.9k (vs the usual
short edge). A macro shock flips ORB's average edges for a quarter. **Vol circuit-breaker (pause N sessions
after a >X% range day) = REJECTED** — skips too many trades (80 days >4%/yr), costs $30–80k PnL, and makes
the target window *worse* (skips recovery, not losers).

- **Breakeven-after-1.5R = a validated WIN on 137** (BE re-simulator reproduces the engine to $0.00/trade):
  move stop→entry once unrealized ≥ 1.5×risk. Full: **PnL $567k→$579k, max DD −$40.2k→−$30.8k (−24%),
  PF 1.47→1.51**. **Lockbox OOS holds: DD −$16.8k→−$14.2k (−15%), PnL flat, PF 1.53→1.57.** BE-1.0R cuts DD
  further (−$26.8k, PF 1.55) at slightly lower PnL. NOT overfit — improves IS *and* lockbox.
- **Mechanism correction (anti-overfit):** the swan losers did NOT run to huge MFE then give it back —
  median MFE of window losers **0.41R** ≈ all-history 0.39R; only 3/40 reached 2R. So an *extreme* 2R BE
  barely helps; the win is the **moderate 1–1.5R** BE catching the common "wide-stop pokes ~1R then fails"
  pattern across all 16y. It's a broad edge, not a swan patch. Next: add `be_after_R` to ORB_3_0/3_1 as a
  param + Auto-Validate it (candidate deployable — cheapest DD reduction found so far).
- **Time-of-day (full history):** edge is a *morning* phenomenon — 09:30–10:30 PF ~1.8 (+$307k of the total),
  12:00–13:00 lunch chop PF 1.11. Confirms §4.9. (In the Apr-2025 window this inverted.)
- **`close_confirm` (already coded in ORB_3_0.py) is HARMFUL on 137:** $567k→**$175k**, PF 1.47→1.14 —
  entering at the bar CLOSE (vs the range edge) worsens the fill on every real break (~$100/trade × 3,900 ≈
  the whole drop), dwarfing the false-wick savings. **Contradicts the reconcile "+$30k" claim → see §6 TODO.**

### 4.14 BE sweep, gap-free 0.9→2.5 · in-sample vs lockbox (2026-07-11) — run #156

Full `be_after_R` sweep in **0.1 steps, no gaps**, on the #137-lock (NQ 5m, or1/stop1.75/tgt4.5R/vol1.25/
atr0.1/Both). Each level is an **independent** backtest of the optimize window AND the held-out last-12mo
lockbox (own DD/PF), so the risk-adjusted read is honest. Anchor `be=0` reproduces #137 to the dollar
(opt $481,605 + lockbox $85,692 = **$567,297**).

| be_R | IS net | IS DD | IS MAR | LB net | LB DD | LB MAR | LB PF |
|---|---|---|---|---|---|---|---|
| 0.0 (no BE) | $481,605 | $38,730 | 12.4 | $85,692 | $16,779 | 5.1 | 1.51 |
| 0.9 | $493,076 | $26,146 | 18.9 | $78,491 | $14,354 | 5.5 | 1.55 |
| **1.0 ★** | $493,105 | **$23,826** | **20.7** | $81,072 | **$11,491** | **7.1** | 1.54 |
| 1.1 | $493,875 | $25,486 | 19.4 | $79,577 | $12,070 | 6.6 | 1.53 |
| 1.2 | $503,664 | $25,486 | 19.8 | $86,647 | $12,974 | 6.7 | 1.57 |
| 1.3 | $500,149 | $25,486 | 19.6 | $86,352 | $13,914 | 6.2 | 1.56 |
| 1.4–1.5 | ~$495k | $29,308 | ~16.9 | ~$86k | $14,239 | 6.0 | 1.55 |
| 1.6–2.0 | ~$487k | $35–37k | ~13.5 | ~$85k | $14,239 | ~6.0 | ~1.53 |
| 2.1–2.6 | ~$482k | $37–39k | ~12.8 | ~$87k | $16,779 | **5.1** | 1.53 |

- **`be=1.0R` is the champion — best MAR in BOTH windows** (IS 20.7, LB 7.1); DD −38% IS ($38.7k→$23.8k),
  −32% LB ($16.8k→$11.5k) for a trivial PnL give-up. Robust plateau **0.9–1.3R**. Full-window: $574,177,
  DD −$26,763, PF 1.55, **MAR 21.5** (== run #154).
- **Why #153's raw pick (2.6R) is hollow:** BE only ever *costs* a sliver of PnL, so a PnL-max objective
  drifts to a high `be_after_R` that barely triggers ≈ plain #137 — by 2.1–2.6R the lockbox DD/MAR are back
  to the no-BE baseline ($16.8k / 5.1). It's not doing BE's job (cutting DD); the gate rightly flagged it WEAK.
  The right objective for a DD lever is **MAR, not PnL** (see §5.1, §5.5).
- Tooling: `tools/orb_be_sweep.py` (re-runnable). Saved as **run #156** ("BE sweep 0.9-2.5 · 137-locked").

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
   `python tools/orb_edge_report.py`. **The 3× cap isn't just realism — it *improves* MAR:** uncapped, the
   rule occasionally sizes ~22× base (bloating drawdown); capping at 3× lifts full-history MAR **71.5 → 96.1**
   ($921k → $590k net, biggest position 3× base). The web report card's overlay uses the 3× cap.

---

## 6. Backlog — investigation TODO (by expected payoff)

| # | idea | expected payoff | status | result |
|---|---|---|---|---|
| **J** | **Candle-confirmation / close-confirm reconciliation** — `close_confirm` (enter on bar CLOSE beyond the range, skipping false-wick breaks) is ALREADY coded in `ORB_3_0.py`. `tools/reconcile.py` says TV's close-based model skipped 306 false wicks (−$149,562) and netted **+$30k** more than the engine over 15y. BUT tested on **137's config** `close_confirm=True` is **−$392k** ($567k→$175k, PF 1.47→1.14) because entering at the close worsens the fill on every real break. | **HIGH** (reconciles engine↔TV; possible new version) | ☐ TODO | **CONTRADICTION to resolve** — is TV's edge a *level-fill* skip (same entry price, just drop the fakes) vs the engine's *close-price* fill? Re-implement close_confirm as "confirm on close, fill at the range level next bar" and re-test; that may be the real TV-matching win. Config-dependent — wide-stop 137 hates it. |
| **H** | **Breakeven-after-R** (`be_after_R` param) — move stop→entry once unrealized ≥ X·risk | **HIGH** | ☑ DONE → **run #154 PASS** | **Fine sweep (0.1 steps, 0–4R; §4.13):** NOT monotonic — **0.1–0.5R is a trap** (lockbox PF collapses to 1.27–1.34); **0.9–1.3R = robust plateau** (full DD ~−30%, LB PF 1.55–1.59, MAR 20–21.5 vs 14.1); ≥1.6R fades to baseline. **Run #153** (free search): picked noise 2.6R → **WEAK/PBO-fail** — the IS PnL objective can't see a DD lever; gates caught it. **Run #154** (pinned **1.0R**, 137-lock): **PASS 5/5 applicable gates**, whole-run **DD −$40,233→−$26,763 (−33%)**, net $574k, PF 1.55, MAR 14.1→21.5, MC-P95 DD improved −$39.7k→−$36.9k; same 3,951 trades. File: `ORB_3_0_BE.py`. Caveat: the 1.0R level was picked on a sweep that saw the lockbox (defense: wide flat plateau). **BE-1.0R is the new best single-lot ORB 3.0 deploy candidate.** Gap-free 0.9→2.5 sweep with an independent lockbox split (**run #156**, §4.14) re-confirms 1.0R as the MAR champion in BOTH windows (IS 20.7, LB 7.1). |
| **K** | **Dynamic / alternative breakeven triggers** — the R-multiple trigger (item H) is one of many possible "arm BE now" signals. Candidates: **time-based** (BE after N bars in trade), **ATR-based** (unrealized ≥ X × session ATR), **OR-width multiple** (price has traveled ≥ X × range width — decouples from stop_frac), **structure** (first higher-low / lower-high after entry), **vol-scaled R** (tighter arm on high-vol days). Owner idea 2026-07-10. | MED-HIGH (item H already banked −33% DD; this asks if a smarter trigger beats static 1.0R) | ☐ TODO | Test in the ORB_3_0_BE re-simulator first (fast), lockbox-check anything that wins; beware: 5 trigger families × thresholds = big selection surface, so demand a plateau + OOS hold like H did. |
| **L** | **Param-vs-RISK charts in the run report** — the 2C/2E/2J/2K charts plot each config's **PnL** only, so a drawdown lever like `be_after_R` looks FLAT and its real effect (DD −33%) is invisible; #153's PDP "peak" at 2.6R was a ±2% PnL ripple. Fix: carry `dd`/`mar` per config in the saved `points` rows (engine `history.py`/`optimize.py`) + a metric toggle (PnL / MAX DD / MAR) on the 2C·2E·2J·2K charts. | **HIGH** (web+engine feature — makes risk levers visible & rankable in the report) | ☑ DONE (v50.8 web + engine; demo run #155) | **SHIPPED 2026-07-10.** Engine: every grid/auto/validate run stores per-config `dd` (drawdown magnitude) in the saved points. Web: CHART METRIC toggle (NET $ / MAX DD / MAR ×100) above 2B re-plots 2B·2C·2H·2I·2J. Proof = run **#155** (BE sweep, 137-locked): PnL view is flat (±2%) but MAX DD view shows the 0.9–1.3R valley ($26.8k vs $40.2k at be=0). Older runs show a "re-run to record it" note. NB: the v49.5 per-column VALUE-filter menus were a separate feature and were REVERTED (v50.9) after they could hide the whole runs list — do not confuse the two. |
| E | **Ensemble** — 1 lot full-ride + 1 lot trailed → blended curve between MAR 15 and 33 (your original 2-contract idea, done right) | MED (smoothing, not new edge) | ☐ TODO | — |
| — | Smarter trailing (chandelier / activate / breakeven) | — | ☑ DONE | chandelier overfits; activate hurts; breakeven wash. **Simple bar-trail wins.** |
| A | **Vol-target (risk-parity) sizing** | HIGH | ☑ DONE | **WIN (modest, generalizes)** — lockbox MAR +29% (6.9→8.9), DD ~halved, PF→1.73, survives lockbox + 4/6 WF folds. Best = `rp-cap3` overlay (§4.7, deploy rule §5.6). |
| B | **Regime skip** (`atr_filter`) | MED-HIGH | ☑ DONE | **NO help** (§4.8) — every filter>0 lowers MAR/PF/PnL, DD doesn't improve. The trail already neutralizes low-vol days (substitutes, not complements). Leave off. |
| C | **Time structure** (`ORB_3_3.py`) | MED | ☑ DONE | time-stop ✗ (cuts winners); **entry-time cutoff = real quality signal** (first-hour PF 2.2, lockbox 3.5, 6/6 WF folds) but quality-vs-quantity on raw MAR → spawned item **G** (§4.9). |
| **G** | **Entry-time × sizing combo** | HIGH | ☑ DONE | **WIN** (§4.10). Time-tilt × risk-parity *stack*: lockbox MAR +85% (6.9→12.7), 5/6 WF folds. Truncation ✗ — tilt, don't cut. |
| **D** | **Long/short asymmetry** | MED | ☑ DONE | **WIN — shorts carry the edge** (§4.11). LONG PF 1.03 (deadweight) vs SHORT PF 2.74; holds on lockbox + ES. Short-tilt stacks → full stack lockbox MAR **15.0 (+118%)**, PF 2.85. Deploy short-tilt not short-only. |
| **F** | **Consolidate — durable code + sizing/MAR in the app** | HIGH leverage | ☑ DONE | `augur_engine/sizing.py` (rp × time × side overlay); `tools/orb_edge_report.py` + `tools/orb_sized_backtest.py`; `run_grid(rank_by="mar")`; `history.py` `mar` field. **Live in the web app:** MAR column (v44.5) + the **SIZING OVERLAY card on ORB run reports** with an **interactive "▶ Compute exact overlay for this run" button (v44.8)** — queues a sized backtest, renders baseline-vs-sized MAR/PF on the report card. `engine.run_backtest(sizing=…)` + runner `sizing` passthrough are the plumbing. **ORB sizing feature fully on the site.** |
| — | ES transfer (base config + long/short + full sizing stack) | — | ☑ DONE | **PASS all three** — base ES lockbox PF 1.57; long/short asymmetry transfers; **full sizing stack transfers** (ES lockbox MAR 5.0→13.5 = +170%, PF→3.10). |
| — | Walk-forward + lockbox of the scale-out | — | ☑ DONE | **PASS** (6/6 folds, lockbox PF 1.63) |

**Recommended next:** edge-hunting is done; wins shipped/built where safe. The 3-lever sizing overlay
is now a **first-class engine call** (`run_backtest(sizing=…)`, runnable via `tools/orb_sized_backtest.py`)
and the **MAR column is live (v44.5)**. The overlay is *built but NOT deployed to the web* by request.
The only remaining step is the **live web sizing toggle** (add a runner `sized_backtest` job + a UI button;
edits `index.html`, so it's the deliberate "take it live" action — owner does it when ready). Everything
else is minor (E: ride+trailed ensemble). Or just **deploy the §5.6 rule** at the execution layer.

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
- **⚠️ The lockbox is now OVER-USED** — the reserved last-12-months has been peeked at many times
  (trail, scale-out, sizing, time, side, ES, cap). Each look erodes its held-out value; after this many
  it's effectively an extension of the in-sample set. **The only clean forward test left is LIVE
  performance.** Treat the lockbox MARs as encouraging, not confirmatory. A future clean read needs a
  fresh, never-touched reserved slice.
- **Overlay weights were chosen post-hoc** — morning ×2 / short ×1.5 / 3× cap are a-priori (un-tuned,
  which limits overfit) but the *directions* were picked after seeing the splits. Some selection bias baked in.
- **Slippage may bite the overlay hardest** — the sizing rule concentrates size onto tight-stop (tiny-OR)
  morning trades, which are the *most* fill-sensitive (small range, stop/market entries). Flat 0.25pt
  slippage likely understates cost exactly where the overlay bets biggest — haircut the sized numbers in your head.
- **Short-tilt is regime-untested** — the short edge is measured over a 2010-2026 secular bull, never broken
  down by year/regime. It could concentrate in a few risk-off years. Deploy the *tilt* (not hard short-only),
  and see the open dive below before sizing it up.
- **§4 tables are UNCAPPED; the deployable is CAPPED** — the §4.10/4.11 deploy-stack numbers (full MAR 71.5,
  lockbox 15.0) are the uncapped research frontier. The tradeable rule (§5.6 + the app card) caps at 3× →
  full MAR 96.1 / $590k net. Read §4 as "how big is the edge," §5.6 as "what you'd actually trade."

---

## 9. Open dive (the one worth doing)

**Sub-period / regime stability of the short-side edge.** Everything hinges on shorts carrying the edge
(PF 2.74 vs longs 1.03) — but that's an aggregate over 16 years. Before trusting a short-tilted book, break
the short edge down **by calendar year and by vol regime**: is it steady, or does it live in 2018/2020/2022
risk-off spikes? If the short PF is positive in most years it's structural and safe to tilt; if it's a few
crash years carrying the rest, the tilt is a bet on volatility returning. This is cheap (reuse the deployable
trade log, group by year/VIX-regime) and it's the last thing standing between "measured edge" and "deployable
with confidence." *(Not yet run.)*

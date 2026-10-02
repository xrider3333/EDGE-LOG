# ENGU-Q — status, results & open work

> Living handoff doc, same shape as `ORB.md` / `NOISE.md`.
> **Created 2026-08-20** (Claude Code). Background: memory `engu-q-project`,
> forward-test wiring in `PAPER_TRADING.md`.

**The family CROWN, as of 2026-09-05, is run #309** — see the CROWN CHANGE section
directly below for the full evidence. It runs `augur_strategies/ENGUQ_1M_ETH_ER_1_0.py`
(the same file as the efficiency-gated #265 leg, but a different cell of its search
space — the efficiency gate is OFF, `er_th=0.0`), every knob pinned:

```
buf_atr 0.3 · tl_len 206 · trail_frac 2.5 · ema_len 220 · atr_len 52 · act_R 1.5
breakeven_R 3.0 · limit_atr 0.55 · er_len 100 · stop_mult 1.3 · regime_len 10
min_brk 1.6 · vol_mult 1.1 · er_th 0.0 (efficiency gate OFF)
```

It is **long only** (`DIRECTION = "LONG"`): a green candle breaking a descending trendline
of recent lower highs, above the trend EMA, on a volume spike; stop at the swing low;
trailing exit; resting limit entry 0.55 ATR below the signal close.

The prior crown was the **frozen clock-scaled #149 transfer, ETH-scaled (#226)** —
`augur_strategies/ENGUQ_1M_ETH_FROZEN_1_0.py`, every knob pinned:

```
tl_len 170 · ema_len 1380 · atr_len 106 · buf_atr 0.9 · vol_mult 0.8
stop_mult 1.0 · act_R 2.5 · trail_frac 2.5 · min_brk 1.3 · breakeven_R 1.5
regime_len 0 (OFF)
```

#226 is not deleted or reinstated as a running leg over this — it stays the documented
control everywhere it is cited (its own run doc, `LEG_SOURCE["ENGUQ"]` in
`api/paper.py`), even though it has not actually been an active nightly PAPER leg since
2026-08-21 (superseded there by the #265 efficiency-gated pair, unrelated to today's
change). The PAPER board's shadow engine now runs, side by side: `ENGUQ_309` (the new
crown, live from 2026-09-05), `ENGUQ_ER` / `ENGUQ_ER_H` (the #265 pair — the outgoing
paper control, deliberately left running), and `ENGUQ_L50` (its own active
pre-registered hybrid test, unrelated to this change). See `PAPER_TRADING.md`.

---

## 👑 CROWN CHANGE 2026-09-08 — the crown moves to run #335 (R2: the #309 knobs with breakeven 2.0 R and stop 1.0)

**Owner decision, 2026-09-08:** *"crown R2 once the validate passes, swap the paper leg."*
The validate posted as **run #335, verdict PASS** (checks 6/6: plateau, wfe, sample,
consistency, pbo, luck; walk-forward folds held **8 of 8**, WFE 1.405, DSR 0.997; plateau
HIGH GROUND 24/24; PBO 0.385 = "some overfit risk"; lockbox pass=true, 129 trades / PF 1.53),
and the crown moved the same evening. **NinjaTrader followed at 21:41** (owner: *"go for all"*):
`EdgeLogENGUQ1m` now runs the R2 knobs exactly (TlLen 206, EmaLen 220, BufAtr 0.3, MinBrk 1.6,
AtrLen 52, VolMult 1.1, StopMult 1.0, ActR 1.5, TrailFrac 2.5, BreakevenR 2.0, LimitAtr 0.55,
RegimeLen 10, ErLen 100, ErTh 0.0) after the RegimeLen build was deployed with NT stopped. The
port's limit-entry, efficiency-ratio and regime paths had never run live before this night, so
the nightly reconcile against paper leg `ENGUQ_335` is the parity check from 2026-09-09 on —
any divergence there is a PORT bug until proven otherwise.

**What R2 is:** `augur_strategies/ENGUQ_1M_ETH_R2_1_0.py`, a sibling of the #309 file with the
trading logic untouched and two defaults moved — `breakeven_R` 3.0 → **2.0** and
`stop_mult` 1.3 → **1.0**. #309's own search maximised net and drawdown, never MAR or R per
year, and pushed the breakeven to the top of its range so the stop almost never interfered;
that is why 58% of its net sat in ten trades with a 282-day hold.

Measured continuously with `tools/queue_guard.py` (entry-sliced, same window, costs and split
as the #309 table below):

| | run #335 / R2 defaults (new crown) | run #309 (outgoing crown, now the control) |
|---|---|---|
| selection (→2025-06-30) | n=1,830 · PF 1.714 · net $522,613 · DD $38,687 · EV R 0.505 · R/YR 61.7 | n=1,505 · PF 1.661 · net $505,756 · DD $44,403 · EV R 0.439 · R/YR 43.9 |
| held-out year | n=118 · PF 1.675 · net $88,380 · DD $41,534 · EV R 0.487 · R/YR 57.5 | n=99 · PF 1.620 · net $85,511 · EV R 0.407 · R/YR 40.4 |
| top-10 share of selection net | 52% | 53% |
| longest hold | 142 days | 282 days |

R2 wins every read and nothing is traded away. Selection check on pre-lockbox data only:
be 1.5 / stop 1.0 ranks first and be 2.0 second by a hair (MAR 0.90 vs 0.96); the owner chose
be 2.0 for dominating every read and winning the held-out year, and every cell that beat the
crown pre-lockbox also beat it in the held-out year. Caveat carried over from the queue note:
era split 2-2, not 4-0 (PF slips 2010-14 and 2018-22, improves 2014-18 and 2022-26).

- **The honest note, said plainly:** run #335 searched the **whole file** — every knob open
  except the two fenced ones — and its own best cell (`validate.champion`) is a **different
  configuration**: ema_len 1340, tl_len 238, trail_frac 4.0, atr_len 28, act_R 2.5,
  breakeven_R 1.0, limit_atr 0.1, vol_mult 0.0, regime_len 5, min_brk 1.4. That cell is
  IS 870 trades / PF 2.26 (first-75% score), whole window 1,344 trades / PF 1.82 / $541k,
  and its entry-sliced held-out year is **weaker** than the R2 defaults: 128 trades / PF
  1.455 / $49,812 / DD $47,779 against 118 / 1.675 / $88,380 / $41,534. It also carries the
  early breakeven (1.0 R) that memory `edgelog-evr-gameable-by-breakeven` warns about.
  **The paper leg therefore trades the R2 DEFAULTS the owner compared and chose; run #335
  certifies the landscape, not that cell.** Owner, later the same evening ("go for all"):
  that cell now rides BESIDE the crown as a forward-test leg `ENGUQ_335_VC` on both boards
  (control = `ENGUQ_335`), so the two cells are judged on the same live tape from here on.
  It is not the crown and NinjaTrader does not run it (NinjaTrader runs the R2 defaults, see above).
- **#309 stays on the board as the control.** Same lineage, same window, only the breakeven
  and stop differ, so any gap between the two rows from 2026-09-08 on is those two knobs
  and nothing else. Its chip reads "ex-crown · control".
- **Recorded where:** `index.html` PAPER_LEG_DEFS gets `ENGUQ_335` (crown chip, `ctrl:
  ENGUQ_309`) and `ENGUQ_309` loses the crown; `api/paper.py` gets `ENGUQ_335 =
  dict(ENGUQ_309, breakeven_R=2.0, stop_mult=1.0)`, `LEG_LIVE_FROM["ENGUQ_335"] =
  "2026-09-08"`, a `LEG_SOURCE["ENGUQ_335"]` provenance block and a new `PAPER_LEGS` row —
  no ML gate. The KEEL / compression overlay legs keep #309 as their base and control.
- **Background:** the research finding is the 2026-09-08 subsection under the 09-05 section
  ("R2 sibling measured continuously") and `BOOKMARKS.md` B25; the `{}`-params trap it
  exposed is fixed since v73.574 (`tools/queue_guard.py`).

## 👑 CROWN CHANGE 2026-09-05 — the ENGU-Q family crown moves to run #309

**Owner decision, 2026-09-05:** *"crown #309 and swap the paper leg to it."* The ENGU-Q
family champion moves from the frozen clock-scaled #149 transfer (run #226) to **run
#309** — `augur_strategies/ENGUQ_1M_ETH_ER_1_0.py` with `er_th=0.0` (efficiency gate
off), a different cell of the same file's search space as the #265 efficiency-gated
leg. Canonical run: **#309**, verdict **PASS** (checks 6/6: plateau, wfe, sample,
consistency, pbo, luck; walk-forward folds held 6 of 8; lockbox pass=true).

Measured today with `tools/continuous_lb_check.py` (one continuous backtest,
2010-06-07 → 2026-06-30, NQ 1m ETH, `db_noadj_eth`, cost 0.533, mult 20, trades sliced
by ENTRY time):

| | run #309 (new crown) | run #226 (outgoing crown) |
|---|---|---|
| selection (→2025-06-30) | n=1,505 · PF 1.661 · net $505,756 · DD $44,403 · EV R 0.439 · R/YR 43.9 | n=2,655 · PF 1.303 · EV R 0.227 · R/YR 40.0 |
| held-out year | n=99 · PF 1.620 · net $85,511 · EV R 0.407 · R/YR 40.4 | n=188 · PF 1.493 · EV R 0.364 · R/YR 68.5 |
| top-10 share of selection net | 53% | 80% |
| ex-top-10 selection net | $235,741 | $67,297 |
| longest hold | 282 days | 105 days |
| reload-vs-continuous lockbox | 112 vs 99 | 212 vs 188 |

Whole-window parity (confirms the params dict below matches the run doc, not a typo):
n=1,604 · PF 1.655 · net $591,267, against the run doc's own `validate.total_trades`
of 1,604.

- **Why the owner crowned it — the family's own EV R / R-YR yardstick (memory
  `edgelog-round6-evr-ryr`):** #309 wins selection EV R (0.439 vs 0.227), selection
  R/YR (43.9 vs 40.0) and held-out EV R (0.407 vs 0.364), and it is far less
  tail-dependent than #226 — only 53% of its selection net sits in its best ten trades,
  against 80% for #226; take those ten away and #309 still nets $235,741 versus #226's
  $67,297.
- **The one honest mark against it, said plainly:** #309 LOSES on held-out R/YR (40.4
  vs #226's 68.5), because it trades about half as often — 99 lockbox entries against
  188. That is the single number in this whole comparison that argues against the
  swap, which is presumably why the owner said "swap the paper leg" rather than
  "retire #226" — see the next bullet.
- **#226 stays on the board as the control.** Nothing about this change deletes or
  archives run #226: its run doc is untouched, and `LEG_SOURCE["ENGUQ"]` in
  `api/paper.py` keeps it as the permanent documented reference every #309 number above
  is measured against. It simply has not been a running PAPER leg since 2026-08-21
  (see §2), which predates and is unrelated to today's crown move.
- **Recorded where:** `api/paper.py` gets a new `ENGUQ_309` params dict, a
  `LEG_LIVE_FROM["ENGUQ_309"] = "2026-09-05"` entry, a `LEG_SOURCE["ENGUQ_309"]`
  provenance block, and a new `PAPER_LEGS` row — no ML gate on this leg (the run doc's
  own `flags.gate` says "UNGATED WINS PRE-LOCKBOX — no gate earns its keep"). The
  `ENGUQ_ER` / `ENGUQ_ER_H` legs (run #265) and `ENGUQ_L50` (run #249) are **untouched**
  — they stay on the board as the outgoing control and as their own, unrelated, active
  pre-registered hybrid test respectively. The owner can retire either on request.
- **Background:** section 1.0 below (added earlier the same day) is the research
  finding that surfaced #309 as "the ENGU-Q configuration the EV R / R/YR question
  actually points at" — this section is the crowning decision that followed from it.

### 2026-09-07 — `regime_len` units on the crown's file are FROZEN on purpose (not "10 days")

**Verified by grep on origin/main and by measurement.** The 2026-08-26 ETH regime rescale
(commit 6da54db, `rb = regime_len * ETH_BARS_PER_DAY` with `ETH_BARS_PER_DAY = 1091`) was
applied ONLY to `augur_strategies/ENGUQ_1M_ETH_1_0.py` — the frozen #226 file. The three
forks off that lineage (`ENGUQ_1M_ETH_LIM_1_0.py`, `ENGUQ_1M_ETH_ER_1_0.py`,
`ENGUQ_1M_ETH_ERW_1_0.py`) still compute `rb = int(regime_len) * 390`, so on the 24-hour
tape (~1,091 one-minute bars/day) `regime_len` on those three files counts **390-bar
blocks** (~0.36 of an ETH day each), not days. **Run #309 — the crown above, on
`ENGUQ_1M_ETH_ER_1_0.py` — was validated with `regime_len 10`, which is 3,900 bars ≈ 3.6
days, not 10 days.** Any wording elsewhere that reads "#309's regime filter is 10 days" is
wrong; it is ~3.6 days.

**Why it must stay exactly as it is.** Measured on the #309 params, one continuous run
sliced by entry time (NQ 1m ETH 2010-06-07..2026-06-30, split 2025-06-30, cost 0.533,
mult 20):

| regime_len (blocks) | bars | ~days | selection PF / net / EV R | top-10 share | held-out n / PF / net |
|---|---|---|---|---|---|
| 5 | 1,950 | 1.8 | 1.469 / $445,967 / 0.321 | 84% | 30 / 2.503 / $100,965 |
| 7 | 2,730 | 2.5 | 1.566 / $496,005 / 0.383 | 75% | 32 / 4.559 / $109,295 |
| **10 (CROWN)** | 3,900 | 3.6 | **1.661 / $505,756 / 0.439** | 53% | 99 / 1.620 / $85,511 |
| 14 | 5,460 | 5.0 | 1.434 / $365,703 / 0.293 | 74% | 97 / 1.655 / $88,410 |
| 20 | 7,800 | 7.1 | 1.322 / $281,113 / 0.215 | 75% | 106 / 1.337 / $62,400 |
| 28 (= the INTENDED 10 days at 1,091/day) | 10,920 | 10.0 | 1.224 / $203,744 / 0.152 | 88% | 118 / 1.238 / $45,647 |
| off | – | – | 1.284 / $446,125 / 0.189 | 56% | 117 / 1.563 / $132,271 |

The crown's edge lives at the ~3.6-day lookback; a genuine 10-day filter (the "28" row) is
**worse than no filter at all**. Profit sits on a ridge — 7 through 14 blocks are all
within reach of the crown — but the crown's broad base (53% top-10 share) is specific to
10 blocks; every neighbour makes similar money out of far fewer trades (74–88% top-10
share). Rescaling these three files to 1,091 would silently turn the crown into the
28-block row, and runs #309 / #310 / the queued ERW validate would stop reproducing from
their own files — the run #198 lesson (`BACKTESTING_STACK.md` 2026-08-08/2026-09-05). The
NinjaTrader port `EdgeLogENGUQ1m.RegimeLen` (v73.559, `tools/nt/EdgeLogENGUQ1m.cs`)
deliberately mirrors this same 390 math for that reason.

**What changed:** a prominent frozen-unit notice + this table added to the module
docstring of all three files, and the `regime_len` DEFAULT_PARAMS label/tooltip corrected
from "days" to "390-bar blocks" on all three. No executable line touched (verified by
`ast.parse` on each file and by re-running #309's exact params through
`augur_engine.engine.run_backtest`: n=1,604 / PF 1.655 / net $591,267 — unchanged from the
run doc).

### 2026-09-08: R2 sibling measured continuously

`ENGUQ_1M_ETH_R2_1_0.py` — a sibling file that corrects the crown's risk knobs (breakeven 2.0R
/ stop 1.0R) — measured the same way as the crown, continuous and entry-sliced
(`tools/queue_guard.py`, same window/split as the crown table above):

| | run #309 (crown) | R2 sibling |
|---|---|---|
| selection | PF 1.661 · net $505,756 · EV R 0.439 · R/YR 43.9 | PF 1.714 · net $522,613 · EV R 0.505 · R/YR 61.7 |
| lockbox | n=99 · PF 1.620 · net $85,511 · EV R 0.407 · R/YR 40.4 | n=118 · PF 1.675 · net $88,380 · DD $41,534 · EV R 0.487 · R/YR 57.5 |
| top-10 share | 53% | 52% |
| longest hold | 282 d | 142 d |

**R2 beats #309 on every read in this table** — selection and lockbox PF, net, EV R and R/YR
all move the right way, top-10 share is a hair lower, and the longest hold is half as long.
That validate posted as **run #335, verdict PASS**, and the crown moved on 2026-09-08 — see the
CROWN CHANGE 2026-09-08 section at the top; this table is the research finding behind it. See
`BOOKMARKS.md` B25 for the same comparison alongside the round-31 pooled books.

**The `{}`-params trap this comparison caught and fixed.** Before v73.574,
`tools/queue_guard.py --params {}` on the ETH forks (`ENGUQ_1M_ETH_LIM_1_0.py`,
`ENGUQ_1M_ETH_ER_1_0.py`, `ENGUQ_1M_ETH_ERW_1_0.py`, and this new `_R2_1_0.py`) silently fell
back to hardcoded module defaults rather than each file's own `DEFAULT_PARAMS` — on 2026-09-08
it graded R2 on the **#226 parity anchor** (2,838 trades / $432,954) instead of R2's own
defaults, before the bug was caught and fixed. Since v73.574 the guard resolves any omitted
param from the target file's `DEFAULT_PARAMS` and prints the resolved params it actually ran,
so an empty `{}` can no longer silently mean "some other config." The R2 numbers in the table
above are post-fix.

---

## Round 57 (2026-09-14) - which setups are taken

**Result, said plainly: all four entry rules tested are DEAD at selection, and the crown does not
change.** Run #335 / the R2 defaults stay the crown; paper leg `ENGUQ_335` and NinjaTrader are
untouched. No rule got far enough for the cost stress, the R5 replication, the day-shift null or the
lockbox look, so **no null p-value and no lockbox figure exists for any rule**, and no fenced file or
validate was cut. Contract: `ENGUQ_R57_PREREG.md` (committed a7f0811 before any test cell ran).
Full write-up with every cell and every clause: `tools/r37_results/r57_summary.txt`.

**Why this round.** Owner, 2026-09-14: *"run more test. try to improve the frontier ENGUQ model."*
It reopens his note parked on 2026-09-11: ENGU-Q was built to read the **context** of the trade, its
**location**, and the **imbalance** of buyers and sellers, so it should win often at a modest profit
factor — instead it wins 29.4% and is carried by a tail. The lever named there is the ENTRY RULE
(which setups are taken), not exits, stops, sizing or a model. So the round asked one question: does
any single condition known at the signal bar, written into a strategy file and run in the engine,
take better setups than the crown?

### Step 1 — the like-for-like frontier

Thirteen ENGU-Q configs on the same tape, window, cost and split, selection = entries before
2025-06-30 (`tools/r37_results/r57_frontier.txt`). The rows that matter:

| config | trades | win | PF | net | MAR | worst-era top-10 | 2022 | index corr |
|---|---|---|---|---|---|---|---|---|
| **R2 defaults = #335 crown** | 1,831 | 29.4% | 1.717 | $524,745 | 0.90 | 65% | +$7,340 | +0.50 |
| R4 defaults (limit 0.85) | 1,877 | 28.9% | 1.713 | $523,557 | 1.21 | 65% | +$17,489 | +0.43 |
| R5 defaults (limit 0.85 + cap 9,660) | 2,434 | 28.4% | 1.519 | $466,910 | 1.02 | 56% | +$24,796 | +0.26 |
| #309 ex-crown | 1,505 | 33.6% | 1.661 | $505,756 | 0.76 | 70% | −$339 | +0.58 |
| #384 champion (900 trials) | 3,802 | 29.4% | 1.313 | $524,504 | 0.73 | 57% | −$5,673 | +0.49 |
| #380 champion (highest win rate) | 3,120 | 38.2% | 1.257 | $422,255 | 0.39 | 85% | −$60,006 | +0.72 |
| #335 search champion (`ENGUQ_335_VC`) | 1,216 | 16.9% | 1.893 | $491,518 | 0.49 | 108% | −$55,881 | +0.76 |

- **The crown sits on every frontier except tail independence.** R4 ties it on PF (1.713 vs 1.717) and
  its MAR lead is one lower drawdown; R5 leads on tail independence but gives up PF.
- **Nothing in the family wins often at a good PF.** The only config above 33.6% is #380 at 38.2%, and
  it pays with PF 1.257, an 85% worst-era top-10 share and −$60k in 2022. Win rate has so far only
  been bought with PF.
- **Four of the five search champions carry heavy index beta** (#376/#383, #380, #381 and #335's own
  cell: yearly corr with NQ +0.72 to +0.76, 2022 losses of $46k–$67k); #384 avoids that only at PF
  1.313. The plain file defaults are the robust ones.
- On the crown the typical trade barely pays: median winner / median loser is 2.97× against the 2.40×
  a 29.4% win rate needs to break even.

### Step 2 — the winner-vs-loser anatomy at the true signal bar

`tools/r37_results/r57_anatomy.txt`: 160 features on the crown's 1,831 selection trades, measured at
the SIGNAL bar (not the fill), judged with a within-year shuffle so a feature that only tells 2012
from 2022 cannot pass. 30 features separate winners from losers on win rate, and they collapse into
**two factors**:

1. **Volatility / stop size — winners are taken in an active tape with a bigger planned stop.**
   Planned risk as % of price, by fifths: win 23.2 / 25.7 / 27.6 / 32.8 / 37.7%. ATR as % of price:
   24.3% → 36.6%. The bar's ATR percentile against the prior year, ranked inside each year: 22.6 /
   30.8 / 28.0 / 30.0 / 35.6%, equally strong in both eras. Prior-day VIX says the same. The dollar
   tail IS this factor: the 21 best 2020-25 trades had a median stop of 171 pts against 59 for the
   rest. This is §1.3's big-stop finding seen from the entry side.
2. **Daily location / stretch — winners sit nearer to (or below) their daily averages.** Distance
   above the 20-day SMA in daily ATRs, by fifths: win 36.3 / 29.2 / 27.7 / 28.4 / 25.2%; daily RSI(14):
   35.8% → 23.6%; the 50- and 200-day SMAs read the same way. It is carried mostly by 2010-2019, and it
   runs against "above the larger moving averages": far above the ~20-day mean wins LESS.

**What did NOT separate winners from losers** (within-year win p-value):
- **the file's own volume-spike test** (volume vs its 20-bar mean): win by fifth 30.5 / 29.0 / 30.3 /
  29.0 / 28.1% (p 0.94) — among the setups ENGU-Q takes, its imbalance read carries no information;
- breakout size in ATRs (p 0.16); candle body share (p 0.90); close location and upper wick (p 0.77);
- trendline quality: R² (p 0.31), slope (p 0.24), number of lower highs (p 0.47);
- prior-day high (p 0.37), position against round numbers (p 0.97), day of week (p 0.90), whether the
  previous trade won (p 0.33);
- the session clock (Asia / Europe / cash, p 0.22): its only link is net R, through the fixed cost
  weighing more on small overnight stops;
- **the monster winners themselves:** the 36 best trades by R differ from the rest on 0 of 158
  features after correction — they cannot be picked out at signal time;
- a combined model of all 160 features: out-of-period AUC 0.513 and 0.536 (0.50 = a coin flip).

The ceiling this set before any rule was run: dropping the worst in-sample fifth of the strongest
reads lifts the win rate only to 30.4–31.1%.

### Step 3 — four pre-registered entry rules, run in the engine

Each rule is one yes/no check at the signal bar added to the crown's existing filters, one knob at a
time. It runs in the engine, so a skipped signal frees the slot and later signals can take it, exactly
as the live strategy would trade. Control = the same file with the rule off; it reproduced the crown
trade for trade (1,831 / 29.4% / PF 1.717 / $524,745). Each rule was judged ONLY at its pre-declared
centre cell. The main bar: win rate at least +1.0 pt (30.38%), PF at least +0.02 (1.737), net at
least 95%, concentration / era / index checks, and both grid neighbours holding a plateau.

| rule (lens) | centre cell | trades | win (lift) | PF (lift) | net (vs control) | verdict — deciding numbers |
|---|---|---|---|---|---|---|
| **H-A** quiet-tape stand-down (context) | skip when the bar's ATR is in the bottom 20% of the prior year | 1,758 | 30.09% (+0.71) | 1.725 (+0.008) | $526,709 (100.4%) | **DEAD** — win and PF short; the 10 neighbour held no plateau (win +0.25, 2020-25 PF lift −0.009) |
| **H-B** daily stretch cap (location) | skip when > 1.5 daily ATRs above the 20-session mean | 1,511 | 30.05% (+0.66) | 1.860 (+0.143) | $513,754 (97.9%) | **DEAD, near miss** — win short; 2.0 neighbour win +0.39 (needs +0.5); 1.0 neighbour net $450,012 (needs $472,271) |
| **H-C** leg recovery floor (location) | skip when < 45% of the falling leg is reclaimed | 1,738 | 29.40% (+0.02) | 1.735 (+0.018) | $528,754 (100.8%) | **DEAD** — win +0.02 (its kill line was +0.75); PF 0.002 short; 2010-19 top-10 share 66.0% (limit 64.1%) |
| **H-D** clock-unit volume (imbalance) | volume ≥ 1.25× the same clock minute's 20-session average, replacing the 20-bar test | 1,687 | 28.99% (−0.40) | 1.651 (−0.067) | $475,161 (90.6%) | **DEAD** — 22 clauses fail; 2022 −$660; added trades PF 0.60 vs removed PF 1.63 |

The look-ahead alarm stayed clear on all four (largest jumps: win +0.71 on H-A, PF +0.143 on H-B,
against +3.0 pts / +0.30). Two independent checks re-ran every cell and rebuilt every feature from
bars up to the signal only: both confirmed, 0 disagreements, no serious finding.

- **H-A.** The skipped signals were 84% Asia, 12% Europe, 0% cash session. A plain stop-size floor that
  skips the same NUMBER of signals (235, only 112 of them the same) gives win +0.87 / PF +0.009 — the
  same order as H-A, so its small lift is consistent with the big-stop / volatility factor, not a new
  edge.
- **H-B — the near miss, said plainly.** It removed late-trend chasing and lifted PF in all four eras
  (2010-13 +0.193, 2014-17 +0.019, 2018-21 +0.310, 2022-25 +0.051), kept 94% of 2022-25 net, and passed
  every concentration, era and index check. It failed on what the owner's framing asked for — win rate
  — and on its plateau. **It stays dead:** no re-tune, and reading it on PF instead of win rate now
  would be choosing the bar after seeing the answer. Any stretch-cap idea is a new pre-registration.
- **H-C.** The mechanism moved as described (limit fills that gapped through fell from 8.4% to 7.7%),
  but the win rate did not.
- **H-D.** The owner's "genuine volume spike", measured against the same minute of prior sessions, adds
  434 steady-hour trades that won 19.4% (PF 0.60, −$88k) and drops 754 that were fine (PF 1.63,
  +$179k); its three cells disagree on the sign of the PF change. It was the weakest-evidence rule
  going in (its anatomy read was not significant).

**Why the trade-list scans over-promised.** Deleting trades from a list predicted win lifts of +1.1
(H-A), +1.0 (H-B) and +1.5 (H-C). In the engine the freed slot is taken by the next signal, and those
refill trades won only 23% (H-A, 116 of them), 21% (H-B, 39) and 14% (H-C, 167), so the real lifts
were +0.71, +0.66 and +0.02. A cut on a trade list is not an entry rule; only the engine run counts.

### What it means for the crown

- **Run #335 / R2 stays the crown, unchanged.** No fenced file, no validate, no new paper leg.
- **No entry filter tested here makes ENGU-Q "win often".** The best centre cell reached 30.09%;
  the only cell of the 12 above +1 pt (H-B at 1.0, 30.8%) gave up 14% of net. The anatomy ceiling
  (dropping the worst fifth of any strong read reaches ~31%) and the frontier (38% only at PF 1.26)
  point the same way.
- **The factors that do separate winners are the ones that already pay.** Big-stop, active-tape
  trades are where the tail lives (§1.1, §1.3); skipping the quiet end drops small-stop losers, but
  the freed slots refill with trades that win only 23%, well below the crown's 29.4%.
- The research file `ENGUQ_1M_ETH_SEL_1_0.py` exists only in the round-57 worktree as a research
  sibling (never to be validated as a four-knob search). All round-57 work is uncommitted pending the
  owner.

---

## §1 — ⚠ THE EDGE IS A HANDFUL OF TRADES (measured 2026-08-20) — READ BEFORE JUDGING A DRAWDOWN

<a id="concentration"></a>

**This is the section to point a session at.** Measured on the deployed #226 config over
NQ 1m ETH, 2018-01-01 → 2026-08-20, n = 1,515 trades, cost 0.533 pts, 1 contract.

### 1.0 ⚠ EV R IS A TAIL DETECTOR ON THIS FAMILY — added 2026-09-05, read before any EV R / R-YR hunt

The owner's cross-strategy reads (EV R = (1−win%)(PF−1); R / YR = EV R × trades per year) are
leverage-blind and instrument-blind, which is why they were adopted. On THIS family they are also
**tail detectors**: every configuration a search has crowned on high EV R turned out to be ten
trades. Measured the same way on the same window (continuous run, 2010-06-07 → 2025-06-30,
`tools/continuous_lb_check.py`, top-10 share = the fraction of net that disappears when the ten
best trades are deleted):

| config | EV R | R / YR | **top-10 share** | longest hold | continuous lockbox trades |
|---|---|---|---|---|---|
| `ER_RYR` (queued R/YR-frontier books) | 1.64 | 91 | **101%** — ex-top-10 it LOSES $3,821 | 179 d | 54 (reload said 84) |
| `ERW` @ trail_frac 5.0 (queued book) | 0.97 | 42 | **104%** — ex-top-10 it LOSES $19,281 | 408 d | 24 (reload said 65) |
| run **#310** LIM (verdict PASS) | 0.94 | 47 | **90%** | **449 d** | **0** (reload said 91) |
| B14 (round-27 R/YR leader) | 0.60 | 93 | 81% | 164 d | 184 (reload said 211) |
| **#226 frozen — DEPLOYED** | 0.23 | 40 | 80% | 105 d | 188 (reload said 212) |
| #265 ER25 (= `ERW` @ trail 2.5) | 0.34 | 29 | 61% | 104 d | 67 (reload said 83) |
| **run #309 crown** — the one that holds up | **0.44** | 44 | **53%** | 282 d | 99 (reload said 112) |

*(The #265 row was labelled "#309 crown" in this table's first version, shipped v73.489 — the params
were lifted from the wrong run doc. Corrected 2026-09-05 and #309's real crown added; the same
`best_params`-not-defaults trap this file warns about elsewhere.)*

**Run #309's crown is the standout, and it is the opposite shape to the artifacts.** Against the
DEPLOYED leg it wins on selection EV R (0.439 vs 0.227) and R / YR (43.9 vs 40.0), wins on lockbox
EV R (0.407 vs 0.364), and is far less tail-dependent (53% vs 80%) — ex-top-10 it still nets
$235,741 against the deployed leg's $67,297. It loses on one read only, lockbox R / YR (40.4 vs
68.5), and for an honest reason: it trades about half as often. Its 282-day longest hold is long,
but it took 99 lockbox entries, so it is a slow exit inside a working config, not a buy-and-hold
masquerading as one. **This is the ENGU-Q configuration the EV R / R / YR question actually points
at — and it is already a validated PASS run, not a new candidate needing a search.**

**The rule the numbers give:** on the 24-hour tape, **EV R ≥ 0.9 has meant a top-10 share ≥ 90%**
in every case tested, and the mechanism is always the same — a wide trailing exit (`trail_frac`
4.0–5.0) with no end-of-day flat never triggers, so one winner becomes a months-long hold and the
"average trade" is that hold. The configs in the 0.23–0.44 band sit at 61–81% instead. Note the
deployed leg is itself at 80%: **concentration alone is not a disqualifier here — it is the house
condition.** What separates an artifact from an edge is whether the config still makes money
without its ten best trades, and whether it goes on trading in the held-out year.

**Therefore, for any EV R / R / YR search on ENGU-Q:** report the top-10 share and the longest hold
beside every EV R, and run the winner through `tools/continuous_lb_check.py` BEFORE queuing a
validate or putting it in a book. A search that ranks on EV R alone will find the buy-and-hold
every time, and the engine's reload-graded lockbox will not catch it (see BACKTESTING_STACK
2026-08-08 / 2026-09-05). Five queued book jobs were annotated in place on 2026-09-05 for exactly
this reason.

### 1.1 The concentration

| measure | value |
|---|---|
| net (2018+) | $358,368 |
| win rate | **27.0%** |
| average trade | +0.168 R |
| **top 10 winners** | **$295,811 = 83% of all net profit** |
| **top 30 winners** | **178% of net** — i.e. every other trade *combined* is negative |
| max drawdown | $50,420 |

**This is not a plateau of winning trades. It is a lottery-ticket distribution.** Owner
2026-08-20, on being shown the numbers: *"idk why we didnt catch that. that doesnt seem
like a platue of winning trades to me."* He is right that it was never surfaced — every
report we had graded it on net / PF / MAR, and all three look healthy while the shape
underneath is this skewed.

**Consequences that follow directly, and should be stated whenever this strategy is discussed:**

- A long run of losers is the *normal* state, not evidence of breakage. Over 2018+,
  **47% of all 6-trade windows contain 5 or more losers.** Streaks of 6+ losers occurred
  63 times; the record is **21 in a row**.
- Any forward-test window short enough to miss a top-10 winner will look like a losing
  strategy, *whether or not anything is wrong*. Paper trading started 2026-08-11 — far too
  short a window to contain one.
- The usual pre-registered bars (net/DD, PF) have very wide confidence intervals on a
  distribution this skewed. See memory `edgelog-netdd-unreliable`.

### 1.2 What is NOT wrong (all checked trade by trade, 2026-08-20)

- **The stop is never violated.** Every single losing trade closes at exactly **−1.00 R**.
  No gap-throughs beyond the modelled open-fill rule, no runaway losses.
- **Big-dollar losses are big *stops*, not broken stops.** Size is always 1 contract while
  stop distance ranges ~29–485 pts, so risk per trade ranges **$585 – $9,716** (median
  $870, p90 $2,878). Record single loss: −$9,716 on 2026-03-23 against a 485-pt stop.
- **August 2026 was a good month in risk terms and a bad one in dollars**: −$6,772 but
  **+3.29 R** total, averaging +0.235 R against the +0.168 R all-time average. All four
  winners had small stops; the two largest-stop trades (207 pt, 233 pt) both lost. That
  mismatch is the entire month. Context: NQ fell 30,338 → 29,207 (−3.7%) over 8/17–8/20.
- Position in the distribution as of 2026-08-20: last-14-trade net at the **17th
  percentile** of all 14-trade windows, last-30 at the **15th**. Below average, inside
  normal. Equity peaked 2026-06-11; drawdown since is $40,932 of a $50,420 record.

### 1.3 Sizing is NOT the answer — do not re-propose it

Equalizing dollar risk per trade is the obvious reaction to §1.2 and it **measures worse**.
Capital-matched (mean size = 1 contract), rolling-median risk parity capped at 3×, same
window:

| rule | net | max DD | MAR |
|---|---|---|---|
| 1 contract (deployed) | $358,368 | $50,420 | **7.11** |
| rolling risk-parity, cap 3× | $155,869 | $29,905 | 5.21 |

It halves the drawdown and cuts the profit by more. The reason is §1.1: the edge lives in
the **big-stop** trades — stops ≥120 pts are 209 trades carrying **$259,410 of the
$358,368 net** — and de-levering them removes the thing that pays. This is a *second*,
independent reason on top of the earlier global-rp rejection (`BACKTESTING_STACK.md`
2026-07-23, "DEAD/REJECTED: S2", where global normalization also de-levered the modern
era). Related memory: `edgelog-transfer-sweep-2026-08`.

Note the one honest caveat: at 1 contract the strategy cannot express risk equalization at
all on NQ. A 233-pt stop is $4,670 minimum. Sizing DOWN would need MNQ micros; sizing UP is
a separate, un-pre-registered question.

### 1.5 ADOPT-CANDIDATE 2026-08-26 — the re-entry cooldown PASSED 5 of 5 (battery V)

**Owner item 896:** *"no strategy should be messing up by taking 5 trades in a row like
that."* First ENGU-Q filter of any kind to clear the bar. Pre-registered in
`tools/enguq_cooldown_test.py` before any result was read; control parity PASS
(n=2843 / $434,721.12 exact); window pinned 2010-06-07 → 2026-06-30.

New knob `cooldown_bars` in `ENGUQ_1M_ETH_1_0.py`, **default 0 = deployed behaviour**:
after a trade closes, ignore entry signals for N 1-minute bars. Causal — it reads only the
bar index of an exit that already happened.

| bars | n | net | Δnet | maxDD | PF | LB net | LB PF | score |
|---|---|---|---|---|---|---|---|---|
| **5** | 2812 | **$452,984** | **+4%** | $50,420 | **1.352** | **$112,591** | **1.608** | **5/5** |
| 15 | 2770 | $431,442 | −1% | $50,420 | 1.332 | $90,412 | 1.451 | 3/5 |
| 30 | 2726 | $432,608 | −0% | $53,212 | 1.335 | $90,606 | 1.443 | 3/5 |
| 60 | 2648 | $471,095 | +8% | $52,911 | 1.382 | $96,538 | 1.474 | 4/5 |
| 120 | 2690 | $498,912 | +15% | $47,331 | 1.440 | $81,611 | 1.423 | 4/5 |
| 240 | 2900 | $325,224 | −25% | $48,864 | 1.294 | $78,284 | 1.436 | 1/5 |

**A single 5/5 cell in a jumpy sweep is the shape of noise, so it was checked before being
believed** (`scratchpad/cooldown_robust.py`, 2026-08-26):

- **It is a PLATEAU, not a spike.** Every value from **3 to 8 bars** lands in the same
  place: net +$16.7k…+$21.9k, PF 1.350–1.355, lockbox PF 1.604–1.612. Bars 1–2 are too
  short to bind (≈ control); 9–12 fall back to ≈ control. Six contiguous cells agreeing is
  not a lucky draw.
- **It does NOT depend on a monster trade.** Given §1.1, the obvious failure mode is
  "kept one more top-10 winner". It did not: the improvement is **exactly +$18,263 whether
  you drop the best 1 or the best 3 trades from both sides** — i.e. the top trades are
  *identical* in both runs. Lockbox likewise, **+$14,102 flat**. The entire gain comes from
  deleting ~31 clustered trades that were net-negative.
- **This is the opposite of every prior result.** Battery U, the 13 risk-tightening
  variants and risk-parity sizing all cut the winners faster than the losers. This cuts
  only losers, because clustering is a distinct, observable defect rather than a general
  attempt to be safer.
- Clustering (re-entry within 5 min of the prior exit) falls **2.1% → 0.7%**, which is the
  behaviour the owner actually complained about.

**NOT YET DEPLOYED — this is a crowning decision, owner's call.** The frozen config still
has no cooldown. Before adopting: run it through the normal validate/lockbox job rather
than this standalone script, and pick within the 3–8 plateau (6 has the best lockbox at
$112,986 / 1.610; 5 was the pre-registered cell).

### 1.4 CLOSED 2026-08-20 — the regime filter FAILED, 0 of 5 cells (battery U)

`regime_len` is **pinned to 0 (off)** in the deployed file, so the only trend gate is
`close > EMA(1380)` — on 1m ETH bars that is roughly **one day** of trend. In a multi-day
slide with sharp intraday bounces, price pops back above a one-day EMA repeatedly and the
strategy buys every bounce. That is exactly the 8/17–8/20 pattern.

Owner 2026-08-20: *"we will ahe to try it with thte filter on."* **This is the sanctioned
next test.** Unlike sizing, it has never been run on the #226 ETH config.

**RESULT (2026-08-20, `scratchpad regime_test.py`, saved as `tools/enguq_regime_test.py`).**
Pre-registered bar: PF ≥ control 1.332, lockbox PF ≥ 1.493, lockbox net ≥ $80k, drawdown
must fall by a larger fraction than net, stuck guard. Mis-scaling handled as required —
regime lengths passed ETH-rescaled (`round(days × 1091/390)`), stated per cell. Control
parity PASS (n=2843 / $434,721.12 exact). Window pinned 2010-06-07 → 2026-06-30.

| days | net | Δnet | max DD | ΔDD | PF | LB net | LB PF | verdict |
|---|---|---|---|---|---|---|---|---|
| 10 | $230,000 | −47% | $70,950 | **+41%** | 1.229 | $52,039 | 1.376 | fail 0/4 |
| 20 | $249,450 | −43% | $55,150 | +9% | 1.268 | $40,235 | 1.270 | fail 0/4 |
| 30 | $256,814 | −41% | $55,543 | +10% | 1.286 | $17,406 | 1.115 | fail 0/4 |
| 50 | $289,291 | −34% | $42,202 | −16% | 1.325 | $65,288 | 1.427 | fail 0/4 |
| 75 | $309,800 | −29% | $51,815 | +3% | 1.345 | $61,934 | 1.366 | fail 1/4 |

**Why it fails, in one sentence: the filter removes the winners faster than the losers.**
Net falls 29–47% in every cell while drawdown mostly RISES (only the 50-day cell cuts it,
and by half as much as it cuts profit). The §1.1 concentration got WORSE, not better — the
top-10 share of 2018+ net went from 0.78 to 0.91–1.03, because the filter deletes mid-size
winners while the monsters (which fire in strong uptrends the filter lets through anyway)
remain. The lockbox collapses in every cell. **This closes the trend-gate family on the
ETH config: the EMA(1380) is doing the useful part of the job already.** The 8/17–8/20
bounce-buying pattern is real but it is the cost of the trades that pay — same lesson as
the 13 risk-tightening failures.

Original pre-registration notes kept below for the record:

What to do, and what to pre-register BEFORE running it:

- **FIXED IN THE ENGINE 2026-08-26 — this step is done, do not redo it.** The constant is
  now `ETH_BARS_PER_DAY = 1091`, so `regime_len` means true days on this ETH file and
  `tools/enguq_regime_test.py` passes days unscaled. Re-running battery U reproduces the
  same windows; the compensation simply moved from the caller into the engine. Original
  finding kept below. **FIRST, fix a mis-scaling — verified 2026-08-20.** `run_backtest`
  computed the regime window as `rb = regime_len * 390`, commented *"390 RTH bars/day"*
  (`ENGUQ_1M_ETH_1_0.py`, in the `if int(regime_len) > 0:` block). This ETH file scaled
  `ema_len` / `tl_len` / `atr_len` by ~×3.54 for the 24h tape but **left this 390 alone**,
  so on ETH bars `regime_len=20` is really ~5.7 days, not 20. Any regime sweep run as-is
  is sweeping the wrong lengths. Either pass ETH-scaled values knowingly, or fix the
  constant to ~1,380 — and say which in the pre-registration.
- Grid used elsewhere in the file's presets: `[0, 20, 30, 50, 75]`.
- Pre-register the bar before running, in this file, with a date. The house standard is a
  lockbox-held improvement, not an in-sample one — and given §1.1, judge on **PF and the
  lockbox slice**, not net/DD.
- Expect a filter to *cut* net: it will remove bounce-buying in downtrends but also remove
  some of the top-10 winners, which is where all the money is. The interesting outcome is
  a drawdown reduction that costs less than proportional profit.
- Matched control: the deployed `regime_len 0` run over the identical window. Pin
  `date_from`/`date_to` to the baseline — see memory `edgelog-rerun-window-pinning`.

Reproduce the §1 numbers: load `find_master('NQ','1m','eth')` from 2018-01-01,
`run_backtest(..., return_trades=True)` with the pinned params above; each trade tuple is
`(entry_bar, exit_bar, pnl_pts, 1, entry_px)` and per-trade risk is
`entry_px - low[entry_bar-170 : entry_bar+1].min()`.

---

## §1B — THE EFFICIENCY GATE (found 2026-08-21, battery V/W) — first gate that ever survived

Owner directive: higher-timeframe / momentum-quality confirmation, NOISE-style. Seven
gates tested on both entries, pre-registered bar (PF +0.02, LB PF and LB net ≥ control,
net ≥ 85% of control, stuck guard). Six died: session VWAP, 15m momentum, 60m momentum,
ATR expansion, higher-lows structure, and efficiency at the stricter 0.35 floor.

**The survivor: Kaufman efficiency ratio of the last 60 minutes ≥ 0.25 at the signal**
(`ENGUQ_1M_ETH_ER_1_0.py`; pinned card `ENGUQ_1M_ETH_ER25_1_0.py`; drivers
`tools/enguq_htf_battery.py` / `enguq_er_robust.py` / `enguq_er_final.py`). Raw entry:

| | control #226 | ER-gated |
|---|---|---|
| trades | 2,843 | **1,336** (−53%) |
| net | $434,721 | **$486,413** |
| PF | 1.332 | **1.597** |
| lockbox | $98,488 / PF 1.493 (188 tr) | **$146,231 / PF 2.645** (67 tr) |
| top-10 share (2018+) | 0.78 | **0.70** |

Robustness: PF gain holds in **all four eras** (gated 1.50–1.67 vs control 1.31–1.37) and
wins **96.4%** of 5,000 paired block bootstraps (CI [−0.018, +0.534], just touching zero
— stronger than the limit-entry find's 94.3%). It also REDUCES the §1.1 concentration.

Caveats, recorded before anyone gets excited: only **67 lockbox trades**; the plateau is
**one-sided** (0.30 collapses the lockbox — never raise the floor); the pairing with the
limit-0.50 entry is weaker (84.5%), so the candidate is the RAW entry; and the §1.4
regime-gate lesson says trend-LEVEL gates fail — this is a move-QUALITY gate, which is
why it behaves differently (it deletes churn signals, not winners).

## §2 — Forward test

**2026-09-05 — the ENGU-Q family crown moves to run #309** (owner: "crown #309 and
swap the paper leg to it"; full evidence in the CROWN CHANGE section above). The board
adds one leg and touches nothing else:

- **ENGUQ_309** — run #309, the new family crown. Live from 2026-09-05. No ML gate (the
  run doc's own gate check says ungated wins pre-lockbox).
- **ENGUQ_ER / ENGUQ_ER_H** — unchanged, run #265's pair. This IS the outgoing paper
  control (what #309 is replacing as the crown), deliberately left running so the
  switch itself is observable.
- **ENGUQ_L50** — unchanged. Its own, unrelated, active pre-registered hybrid test.

**2026-08-21 — the #226 raw leg is RETIRED from paper** (owner: "replace the old enguq and put
the top hybrid on there as well"). The board now carries:

- **ENGUQ_ER** — run #265, the efficiency-gated config (§1B), raw entry. Live from 2026-08-21.
- **ENGUQ_ER_H** — the same backtest with #265's crowned logistic@0.55 hybrid overlay. A
  forward TEST, not a crown: on the held-out year the overlay did not beat ungated (recovery
  5.69 vs 5.86), so the pre-registered claim is simply "ENGUQ_ER_H beats ENGUQ_ER on recovery
  from 2026-08-21 on". One backtest, two rows; ENGUQ_ER is the exact control. The rf hybrid
  (lockbox PF 5.80 on 22 trades) was deliberately NOT chosen: its pre-lockbox row is worse
  than ungated, so picking it would be hindsight — the NOISE_H lesson.
- **ENGUQ_L50** — unchanged. Note it lost its matched control when #226 left the board.

The original pair, for the record:

Two legs run side by side on the PAPER board, as a matched pair:

- **ENGU-Q RAW** — the #226 config above, live from 2026-08-17.
- **ENGU-Q · LIMIT 0.50** — identical in every knob; the only difference is that it rests a
  limit order 0.50 ATR below the signal close and drops the trade if it does not fill
  within ten bars. Live from 2026-08-18. It **fails** the pre-registered net-per-drawdown
  bar (8.32 vs 8.62) because entering lower against the same stop widens risk. Candidate,
  not a winner.

Both are engine-side; NinjaTrader runs RAW only (`EdgeLogENGUQ1m` on DEMO7240108). See
`PAPER_TRADING.md` and memory `edgelog-paper-trading`.

---

## §3 — Changelog

- **2026-09-14** — **Round 57: four entry rules (which setups are taken) tested against the #335
  crown, all DEAD at selection** — quiet-tape stand-down, daily stretch cap (near miss: PF +0.143 but
  win +0.66 of the +1.0 needed, no plateau), leg recovery floor, clock-unit volume. Pre-registered in
  `ENGUQ_R57_PREREG.md` (a7f0811) before any cell ran; none reached the null, cost stress or lockbox.
  Crown unchanged. See the Round 57 section above.

- **2026-09-08 (evening)** — **CROWN CHANGE → run #335 (R2).** Its Auto-Validate passed (6/6,
  WF 8/8, lockbox held) and the owner's standing instruction fired: paper leg `ENGUQ_335`
  added on both boards trading the R2 defaults, `ENGUQ_309` demoted to the matched control.
  The validate's own best cell is a different configuration with a weaker held-out year —
  stated in the new CROWN CHANGE section, not adopted. NinjaTrader unchanged (#226 port).
- **2026-09-08** — R2 sibling (`ENGUQ_1M_ETH_R2_1_0.py`, corrected breakeven/stop) measured
  continuously against the #309 crown: beats it on every read (selection PF 1.714 vs 1.661,
  R/YR 61.7 vs 43.9; lockbox PF 1.675 vs 1.620, R/YR 57.5 vs 40.4; top-10 share 52% vs 53%;
  longest hold 142 d vs 282 d). Not yet crowned — its own Auto-Validate (job
  `wRUgSS4JeGLlI7muKZ31`) is running. Same-day fix: `tools/queue_guard.py` v73.574 now resolves
  omitted params from each file's own `DEFAULT_PARAMS` instead of silently falling back to
  hardcoded module defaults — the bug had graded R2 on the #226 parity anchor before being
  caught. See the new subsection under CROWN CHANGE above and `BOOKMARKS.md` B25.

- **2026-09-05** — CROWN CHANGE: family crown moves from #226 to run #309 (owner:
  "crown #309 and swap the paper leg to it"). New `ENGUQ_309` PAPER leg added
  (`api/paper.py`), live from 2026-09-05; ENGUQ_ER/ENGUQ_ER_H and ENGUQ_L50 untouched.
  See the CROWN CHANGE section above for the full evidence.

- **2026-08-21** — §1B added: efficiency-ratio gate (er 60 ≥ 0.25) is the first
  confirmation gate ever to survive the pre-registered bar; validate queued on the
  pinned card. Six sibling gates killed the same day.

- **2026-08-20 (later)** — §1.4 CLOSED: regime filter 0-for-5 by the pre-registered bar
  (battery U). Every cell cuts net 29–47%; only one cell cuts drawdown at all and by half
  as much; concentration worsens; lockbox collapses. Trend-gate family closed on this config.
- **2026-08-20** — File created. §1 written after the owner asked why ENGU-Q RAW was
  "hitting a lot of losses recently": the answer is §1.1, the answer is *not* a fault, and
  the sanctioned follow-up is §1.4.

## 2026-09-24 - the certified sealed year of ENGU-Q #335 is ONE trade

Measured on one continuous replay, entry-sliced, pinned to the crown's own window and cost
(NQ 1m ETH, db_noadj_eth, 2010-06-07..2026-06-30, split 2025-06-30, cost 0.533, mult 20; house
parity self-test #226 = 2,843 trades / $434,721.12 PASS).

- Sealed year 2025-06-30..2026-06-30: 118 trades, $88,380, PF 1.675 - the figure on the paper card.
- ONE trade carries all of it: entered 2026-04-07 12:47 ET, exited 2026-05-12 12:41 ET, +$91,157,
  a genuine 35-day hold. That is 103.1% of the sealed net.
- The other 117 sealed trades LOSE $2,776 at PF 0.979.
- The 2024-onward stretch tells the same story: top-10 share 105.7%, ex-top-10 -$14,266 at PF 0.951
  (at round 47's own 0.783 cost convention: 106.3% and -$15,676 at PF 0.946, reproducing
  BOOKMARKS round 47 to the dollar - that record needs no correction).
- Whole window is NOT a tail artifact: 1,949 trades, $613,126, PF 1.711, top-10 share 55.6%,
  ex-top-10 PF 1.316.

**How to read it.** This does not unwind run #335's PASS and does not move the crown: the whole
window is broad, and a single large winner is the documented shape of this family
(`ENGUQ.md` section 1, memory `enguq-384-tail-economics`). What it does mean is that the sealed
year is not independent evidence - it is one trade - so the sealed PF 1.675 must never be quoted as
a forward expectation, and the R3 hold-cap sibling (cap the hold at 8,280 bars) now has a second
independent argument for a per-stretch battery.

## 2026-09-26 - contract-roll correction (ROLL_AUDIT.md)

The roll audit (written 2026-09-25, text in commit 80ab727; read here at 9421861) rebuilt all 64 NQ
and 64 ES contract switches from raw vendor data and re-ran this family on back-adjusted prices. It
changed nothing - no strategy file, no paper leg, no job. ENGU-Q carries more of the correction than
any other family, so the figures below replace the ones they name. (V) = re-run independently and
matched. (M) = measured once. "To be recomputed" means do not quote a number yet.

**A contract roll reaches ENGU-Q three ways, because the family has no roll handling at all.**
1. *Booked carry (V).* A position held through a switch books the contract offset - about $1.5k to
   $6k per NQ contract over 2022-25. On the #335 leg that is $38,985 across 36 crossings.
2. *Stale entry filters (V).* For one to three days after an upward switch the regime average, the
   moving average and the trendline still hold old-contract prices, so extra longs get through. This
   is the bigger half, and one entry dominates: 13 March 2023, a real five-month hold worth $65,121
   that a stale regime average let in. Corrected, it and one loser in the same window become 52
   smaller trades worth $11,677 - about $47.6k of the family's whole change.
3. *Fake stop-outs on a splice bar (V).* The trail is lifted off the bar's high before the low is
   checked, so a bar holding two contracts can stop a long at a price that never traded. ENGU-Q #381
   in June 2026 is the worked example; any trailing long open across the 14 September 2026 splice is
   exposed to the same thing.

**Corrected on back-adjusted prices (the June 2026 splice is NOT adjusted in this block):**
- **#335 book and paper leg** (file defaults, cost 0.783): $603,381 to **$499,155**, down 17%.
  PF 1.694 to 1.534, drawdown $41,889 to $44,205, lockbox by entry $87,790 to $80,729. Only $38,985
  is booked carry; the rest is a different sequence of trades. (V)
- **#335 validate champion** (starred crown, cost 0.533): $541,330 to **$476,435**, PF 1.820 to
  1.699; cold lockbox $58,163 / PF 1.531 to **$43,468 / PF 1.366**. (V)
- **ENGU-Q on ES #370** (PASS, cost 0.40): $381,313 to **$341,487**, PF 2.459 to 2.187, drawdown
  $13,402 to $15,444; cold lockbox $25,372 to $17,261. (V)
- Paper controls: **#309** $591,267 to $494,275 - **#265** $486,053 to $418,006 - **#249** $513,014
  to $407,010 - **#226** $434,721 to $343,583. (all M)
- **#227**, the day-session run behind the QQQ evidence: $453,532 to **$350,542**, drawdown deepens
  34% to $87,683 - the largest drawdown change in the family. (V)
- The other twenty-odd research runs lose 4% to 22%; every cold lockbox keeps its sign. (M)
- Books carrying these legs each lose their leg's delta: the four with the #309 leg (#371, #361,
  #337, #317) lose $96,992 each; the five with the #335 leg (#365, #375, #372, #363, #323) lose
  $104,226 each; #262 carries the day-session leg and loses about $103,000. All stay PASS. (M)

**June 2026 sits on top of that, and most of the combined arithmetic is still owed.** The June
switch is inside the 15 June 03:30 ET bar on NQ at about +293 points, not the 14 June evening jump
earlier work used - that jump is a real weekend gap. Repaired alone, June costs the #335 leg another
$5,860 on both the whole run and the lockbox, ES #370 about $6,824, and hands #381 back $6,305 (it
still FAILs). Those deltas were measured on the raw runs, so every back-adjusted-plus-June figure is
**to be recomputed**, including the cold lockboxes for the #335 champion and for #370. One exception
stands: #370's lockbox read by entry date, **$28,136**. (V)

**What did not change.** ENGU-Q #335 is still the family crown, and its order against #309, #226,
#265 and #249 holds on net, profit factor and the validate lockbox. Every crowned, starred, book and
paper run keeps a positive cold lockbox at profit factor 1 or better; no sign flips. #381 stays
FAIL. The only lockbox that flips is #152, a superseded July run that was never deployed.
Walk-forward folds, PBO and DSR were not re-run for any crown, so those are untested, not confirmed.

**How far back-adjusting was proved safe here - read before running anything.** Over the full window,
shifts of +5,000, -1,000 and the cumulative offset give identical trades for the #335 leg and for
#370 (M). The wider check across other family files used one shift over 2021 to mid-2026 only, one
run per file, champion parameters only (V for that scope). "Every ENGU-Q file is shift-safe" is NOT
established; each file needs the full-window shift test on its own real parameters first.

**The leg-parameter trap, unchanged.** Three cells answer to the same name: the books' ENGU-Q #335
leg is the file's own defaults, 1,949 trades at cost 0.783; #335's saved champion is 1,344 trades at
0.533; a leg queued with no parameters drops through to the function's internal defaults, which is
#226's cell, 2,843 trades / $420,506 - what books #417, #418 and #419 actually ran. Always say which
cell a figure comes from. (V)

**The fix is a re-validate, and it is an owner call.** No ENGU-Q file needs an edit. Order of work:
repair the post-June-2026 data tail, build back-adjusted 1-minute masters (none exist today - the
only adjusted futures series registered are four 5-minute twins with a stale offset that stop
adjusting in March 2026), then re-validate #335 and #370 and restate the evidence behind #309, #226,
#265, #249 and #227. The queue script is prepared and guarded at
`tools/queue_enguq_rolladj_revalidate.py`; it is a dry run unless the owner says go.

**Research ledger row 1.15 is superseded by the audit** (the row already carries the note). It read
23 crossings / $39,580 on the #335 leg and 30 / $33,912 on #370; exact is 36 / $38,985 and 35 /
$24,862, with none of #370's inside its entry-split lockbox, and the full losses including changed
trades are much larger - $104,226 and $39,826. The row leaned on the house seam detector, which
finds only 19 of the 64 NQ switches.

## 2026-09-26 - ENGU-Q on ES: CLOSED-NO

**Decision, taken by the owner through the MANAGER chat on 2026-09-26: the ES/MES paper leg is
CLOSED-NO.** This is a decision, not a new measurement, and the evidence below is recorded with its
honest edges so a future session can re-open it knowingly. Nothing here touches the NQ crown #335.

- **Two grades, one cell.** ENGU-Q #370 (ES 1m 24h, 2010-06-07..2026-06-30, sealed from 2025-06-30)
  at 0.40 points a round trip: PASS 6/6, folds 8/8, 681 trades / $381,313 / PF 2.46 / drawdown
  $13,402, sealed year 67 trades / $25,372 / PF 1.61. ENGU-Q #377, the same cell at the honest 0.60:
  WEAK, folds still 8/8, sealed year still positive at $24,702 / PF 1.59, failing only the overfit
  check at 0.516 against a 0.500 line (#370 reads 0.496). The extra cost removes $6,810, 1.8% of net.
- **Round 46 pre-registered the failure condition** before either grade was read: if it only
  survives at 0.40 it is not a leg. 0.40 on ES is below one tick plus commission.
- **The concentration read is the stronger argument.** On the crown's settings run on ES (rounds
  46-47): only 3 of 16 years stay positive once each year loses its own three biggest trades; over
  2024-2026 the ten best trades are 124% of the stretch and the other 226 trades lose $19,909. On
  #370's own sealed year the ten best trades make $64,852 against a year of $25,372, and the other
  57 trades lose $39,482. The card's own power check reads 0.37 against a 0.80 target.
- **The roll correction takes another tenth off.** 35 of #370's trades cross a contract switch and
  book $24,862 of pure carry, all before the sealed year; back-adjusted the run is $341,487 and the
  sealed year by entry is $28,136 once June is repaired.
- **The honest edges of this closure.** At 0.60 the leg still clears the round-42 cost rule (about
  $98 a trade against a $30 round trip, 3.3x), and the per-stretch concentration test has never been
  run on the cell #370 and #377 actually crowned - only on the crown's NQ settings run on ES. The
  sealed year also has four published values (67 trades / $25,372 reloaded; 16 / $34,960 continuous
  by entry; $107,924 pooled by exit inside a book; $48,073 in the card's own stretch block) and they
  have never been reconciled. To re-open, the minimum is one re-grade at 0.60 on back-adjusted
  prices with June repaired, plus the concentration test on the graded cell.

### 2026-09-27 - the roll-corrected re-validates landed: ENGU-Q #443 (NQ) and #442 (ES)

Owner GO on decision 13. Both jobs named the registered back-adjusted masters explicitly
(db_adj_eth), pinned window, cost, contract value and the sealed year to the runs they correct,
ran 900 trials with the ranges fenced, and finished in about 70 minutes each.

**Both come back WEAK, and neither failure is caused by the roll correction.**
- **ENGU-Q #443 (NQ, corrects #335):** WEAK, failing only the luck check (0.769 against a 0.80
  bar). Folds 7/8, overfit reading 0.222 - BETTER than #335's 0.385. Walk-forward 19.6% a year at
  Sortino 1.42 (against #335's 37.7% and 2.998); sealed year 59.3% a year at Sortino 1.81 on 197
  trades (#335: 58.2% and 2.844 on 129).
- **The budget moved the crown, not the tape.** #443's crowned cell is identical in all 14 knobs
  to ENGU-Q #402's, a 900-trial search run on the UN-corrected tape on 2026-09-20 that was also
  WEAK. Nothing here says the roll fix re-crowned ENGU-Q.
- **ENGU-Q #442 (ES, corrects #370):** WEAK, failing only the overfit check, and failing it badly
  at 0.905. Walk-forward 22.0% a year at Sortino 4.42; the sealed year is TEN trades whose ten best
  are 100% of it. Not evidence. ENGU-Q on ES stays CLOSED-NO; this run corrects the record.

**The number that decides the crown: the defaults cell, run continuously on the corrected tape.**
This is the cell paper leg ENGUQ_335 and NinjaTrader actually trade.

| NQ, cost 0.533 | no-adjust | roll-corrected |
|---|---|---|
| Tuning trades / net / PF / MAR / Sortino | 1,831 / $524,745 / 1.717 / 0.90 / 3.90 | 1,937 / $428,111 / 1.537 / 0.74 / 3.10 |
| Sealed trades / net / PF / MAR / Sortino | 118 / $88,380 / 1.675 / 2.13 / 4.00 | 116 / $75,449 / 1.580 / 1.72 / 3.41 |
| Whole window | 1,949 / $613,126 / 1.711 | 2,053 / $503,560 / 1.543 |

Reconciles to the dollar with the correction section above: at the book's 0.783 cost the corrected
whole run is $493,295, which is that section's $499,155 less the $5,860 June repair - these masters
carry the June switch, which that block excluded.

**On the corrected tape the defaults cell beats both champions.** Against #335's champion
($441,318 tuning / MAR 0.41 / sealed $29,257) and #443's new cell ($379,140 / MAR 0.33 / sealed
$59,301), the defaults cell wins on net, drawdown, annualised MAR and Sortino in both stretches.
Nothing argues for moving the paper or NinjaTrader cell, and ENGU-Q #335 keeps the crown.

**Read these two runs with five caveats.** (1) Not like-for-like in three ways at once: corrected
tape, 900 trials against 300 and 250, and fenced ranges. (2) Every sealed year here is tail - the
corrected defaults cell's ten best trades are 224% of its sealed net, and without them the year is
-$93,484, so the "sealed year of ENGU-Q #335 is one trade" finding survives the correction and gets
worse. (3) #442's sealed year is ten trades. (4) The June 2026 offset behind both sealed years is
ESTIMATED (NQ +293.00, range 288-300) because the raw vendor feed stops 2026-06-05; no trade in any
cell enters or exits on a splice bar, but the estimate sits in the level of every earlier bar.
(5) Shift-invariance was proved for the #335 leg and #370 at their own parameters, not for the two
new cells - if either is sensitive to price level it would read differently on the forward-adjusted
twin.

### 2026-09-27 - the hold cap on roll-corrected prices: FAILS its pre-registered bar

Pre-registered before any measurement (scratch PREREG.md, 12:26): the hold cap earns a validate only
if, against the crown's defaults cell, (a) the sealed-year top-10 share falls at least 30 points AND
the sealed year stays positive AND its profit factor without the ten biggest trades is above 1.0,
(b) tuning net gives up no more than 10%, and (c) tuning annualised MAR does not get worse. All on
the back-adjusted NQ tape, cost 0.533, contract value $20, window 2010-06-07..2026-06-30, sealed
split 2025-06-30, one continuous run per cell sliced by entry. Harness gate: the crown cell
reproduces all nine published baseline quantities, and the hold-cap file with the cap switched off
returns a byte-identical trade list, so every row below is a one-knob comparison.

**Shift-invariance first, because it had never been proved for this file.** Twelve price shifts on
two tapes moved not one entry bar, exit bar or trade count. A last-bit floating-point residue does
appear in the points column (largest 1.8e-11 points, net unchanged to the cent) - the crown cell
shows the same residue at the same size, so it is not a property of the hold cap. Mechanism proved,
not assumed: it is the re-rounding of the resting limit price, the one place a price level meets a
non-tick quantity; set that entry to market and every trade list is bit-identical.

**Every cap fails, and always on the same leg.** Caps 6,900 / 7,820 / 8,280 (the file's default) /
8,740 / 9,660 bars: sealed-year top-10 share falls a lot (48 to 60 points, clause a's first leg
clears everywhere) but the sealed year without its ten biggest trades runs at profit factor 0.548 to
0.585 against the 1.0 required, so clause (a) fails in all five. Clause (c) fails in all five too:
tuning annualised MAR drops from 0.74 to between 0.49 and 0.69. Clause (b) survives except at cap
6,900. Best cell of a failing set is cap 8,740: tuning 2,490 trades / $416,567 / PF 1.437 / drawdown
$40,548 / MAR 0.68, sealed $112,565 with the top-10 share down 60 points.

**What the cap genuinely does, on the measure the house says is the right one.** Rate-matched (k=1
for a one-year stretch), delete the single biggest sealed trade: the crown's sealed year turns into
a $15,708 LOSS at profit factor 0.879, while every capped cell stays positive at 1.23 to 1.42. The
cap also cuts the longest hold from 104 days to 11-15, lifts the sealed sample from 116 trades to
146-172, roughly halves the sealed-year drawdown, and improves tuning years-surviving-three-deletions
from 5 of 16 to 6 or 7. The price is a tuning drawdown up to 35% worse and a lower tuning MAR -
a trade the file's own docstring does not mention.

**Verdict: no validate queued.** The idea is not worthless, but it fails the bar that was written
before the numbers were read, and rescuing it on the rate-matched read afterwards would be fitting
the test to the result. Also noted: the R3 docstring's own table was measured on the un-corrected
tape and does not reproduce here. If this is ever revived it needs a new pre-registration whose
concentration clause is rate-matched from the start, not a re-read of this one.

**Process note.** These local runs were wrapped in the house research beacon, which writes a job
document to the queue so the dials show the work. That is a Firestore write, so "read-only" was not
strictly true of this round; no run number was created and nothing reached the RUNBOARD.

### 2026-09-28 - ENGU-Q #335 restated: drawdown valued daily, the roll-corrected sealed year, and which cell to judge the crown by

MANAGER's ROC audit and ML-edge audit each raised a pair of ENGU-Q #335 figures that did not
reconcile. Every number below was re-measured here, one continuous run per cell over
2010-06-07..2026-06-30 sliced by ENTRY at the 2025-06-30 sealed split, on the registered masters
(NOADJ_NQ_1m_ETH and ADJ_NQ_1m_ETH). Nothing was re-validated and no run number was created.

**Two cells answer to the name ENGU-Q #335, and they disagree about everything.**

| one continuous run, sliced by entry | paper / NinjaTrader cell (file defaults, cost 0.783) | validate champion (starred crown, cost 0.533) |
|---|---|---|
| whole run, no-adjust | 1,949 trades / $603,381 | 1,344 trades / $541,330 |
| whole run, roll-corrected | 2,053 trades / $493,295 | 1,387 trades / $470,575 |
| sealed year, no-adjust | 118 trades / $87,790 | 128 trades / $49,812 |
| sealed year, roll-corrected | 116 trades / $74,869 | **147 trades / $29,257** |
| sealed drawdown booked at close | $44,205 corrected | $47,779 no-adjust / $57,729 corrected |
| sealed drawdown valued daily | $50,443 corrected | **$65,128 no-adjust** / $71,933 corrected |
| sealed return per dollar of drawdown, valued daily | 1.48 | 0.77 no-adjust, 0.41 corrected |

**Drawdown valued daily, because ENGU-Q holds for weeks.** The engine books a loss only when a
trade closes, so a hold that is deep under water for a month shows nothing until the exit. Marked
every day, the validate champion's sealed drawdown is $65,128 against the $47,779 booked at close -
36% deeper, and its sealed return per dollar of drawdown falls from 1.04 to 0.77. MANAGER's audit
reads 1.22 falling to 0.89; that pair divides the validate card's $58,163 by the same continuously
measured drawdowns, which mixes two reads (see the next paragraph). The paper cell suffers far less:
$50,443 valued daily against $44,205 booked, 14% deeper. Two independent reconstructions of the
daily curve agree within 2% ($65,128 marking each ET calendar day's last bar, $63,973 from the
exported leg curve at C:\EdgeLog\book_legs); the conclusion is the same either way.

**Gap one, now closed: $43,468 against $29,257.** Same cell, two methods. $43,468 is a COLD-RELOAD
lockbox measured on a locally built back-adjusted series that did not carry the June 2026 splice.
$29,257 is the same champion cell run continuously on the registered ADJ_NQ_1m_ETH master, which
does carry June, and sliced by entry. The cold reload reads about 17% high on its own (see gap two),
June is worth about $5,860, and the remainder is a different sequence of trades. **Use $29,257 on
147 trades. Retire $43,468 - it is not a like-for-like read of anything.**

**Gap two, now closed: $58,163 on 129 trades against $49,812 on 128.** Same cell, same uncorrected
tape, same window. $58,163 is the validate card's lockbox, which reloads the sealed year cold with
no warm history - the pre-v73.841 convention. $49,812 is the continuous run sliced by entry. The
cold reload therefore reads 16.8% above the honest figure, which is the same 14% overstatement
MANAGER measured from the other direction. **Use $49,812.**

**Roll jumps are 31% of that sealed year.** Three of the champion cell's 128 sealed trades are held
across a quarterly contract switch and book the offset as profit: 14 Sep 2025 (+237.25 points,
$4,745), 14 Dec 2025 (+254.00, $5,080) and June 2026 ($5,860). Together $15,685, or 31.5% of the
$49,812. The June component uses the ESTIMATED +293.00 offset, because the raw vendor feed stops
2026-06-05; the true value is somewhere in 288-300, so that third is worth +/- $100.

**One trade is the whole sealed year, and the roll correction makes that worse, not better.** The
paper cell's sealed year holds one long from 7 April to 12 May 2026, 35 calendar days, worth
$91,152. That is 104% of the uncorrected sealed year of $87,790, and 122% of the roll-corrected
$74,869. Strip it and the remaining 115-117 trades LOSE: -$3,361 uncorrected, -$16,283 corrected.
The champion cell has the same shape with a different trade - one 42-day hold worth $52,498, 105%
of its uncorrected sealed year and 179% of its corrected one. No ENGU-Q sealed-year figure should
ever be quoted forward without this sentence attached.

**Which cell should the crown be judged by: the paper / NinjaTrader cell.** It is the cell paper
leg ENGUQ_335 and NinjaTrader actually trade, so judging the live leg by a cell nobody trades is a
category error on its own. It also wins on the corrected tape on every measure that matters: whole
run $493,295 against $470,575, sealed year $74,869 against $29,257, sealed drawdown valued daily
$50,443 against $71,933, sealed return per dollar of drawdown 1.48 against 0.41. **Recommendation:
the paper / NinjaTrader default cell is the single forward yardstick for ENGU-Q #335, and EXPLORE's
champion row should be read as a search artefact, not as the leg.** The crown itself is unchanged.

**The rf HYBRID gate hurts the cell that is traded, and its apparent win elsewhere is size.** On the
paper cell the rf gate turns a sealed +$74,869 into **-$17,067** (-$16,637 at one contract). On the
champion cell it reads +$110,209, but at an average 2.4 contracts; at one contract that is $33,288
against raw's $49,812. The gate loses on both cells once size is frozen. Confirms MANAGER's note
and extends it to the champion cell.

**#442 and #443 must not carry the roll haircut.** MANAGER's ROC board
(C:\EdgeLog\manager\roc_board_2026-09-27.json) applies the flag "ENGU-Q net ~-17% after roll
correction (re-runs #442/#443)" to every ENGU-Q row including #442's and #443's own, which
double-counts: both runs were searched on the back-adjusted masters and already carry the
correction. Routed to MANAGER; that file is not edited from this lane.

### 2026-09-28 - owner decisions, the new house yardstick, and what ENGU-Q #335 scores on it

Three owner decisions taken through the MANAGER chat on 2026-09-28 (inbox item #16). These are
decisions, not measurements.

1. **ENGU-Q stays paper-only on the Webull book.** No flat-at-close variant will be built or
   re-validated. This closes the question raised by the Webull go-live audit: the Webull book
   flattens ENGU-Q #335 at 15:59 every day while the strategy's edge is multi-day holds, so going
   live there would trade an untested cut-short version. Paper: WB has been told.
2. **The forward yardstick for ENGU-Q #335 is the paper / NinjaTrader DEFAULT cell on
   roll-corrected prices, with the one-trade caveat stated every time.** The validate champion's
   row on COMPARE and EXPLORE is a search artefact, not the leg. Recommended and accepted the same
   day; the measurements behind it are in the section above.
3. **#309, #265, #249 and #227 stay as superseded controls.** They will not be re-run on corrected
   prices. Their roll-corrected figures are recorded in the 2026-09-26 correction section and are
   measured-once (M), not verified; treat them as historical context, never as evidence.

**New OWNER RULE, all lanes: one frontier yardstick.** Rank by ROC % per year at a $30,000 worst
drawdown, with the drawdown valued DAILY - that is simply 30 x annualised MAR. Show the
walk-forward and the lockbox separately, never pooled. Freeze size and every ML or tilt setting
before the lockbox and count only the pre-lockbox pick. A sized or ML version must beat its raw
twin on that number AND on Sortino in both stretches. Minimums: 100 walk-forward trades, 50 lockbox
trades, and the lockbox must stay profitable without its single biggest trade. Keep quoting ROC %
per year at stated size as well, but judge and recommend on this one.

**ENGU-Q #335 scored on the new rule** (paper / NinjaTrader default cell, roll-corrected,
one continuous run, drawdown marked every day):

| stretch | trades | net | drawdown valued daily | annualised MAR | ROC at a $30k drawdown | without its single biggest trade |
|---|---|---|---|---|---|---|
| walk-forward (2016-10 to 2025-06) | 1,167 | $380,348 | $48,599 | 0.89 | **26.6% a year** | +$353,544 - passes |
| lockbox (sealed year) | 116 | $74,869 | $50,485 | 1.58 | **47.4% a year** | **-$16,283 - FAILS** |

The validate champion cell on uncorrected prices reads 20.6% and 24.9% on the same two stretches,
below the paper cell on both, which is the third independent argument for decision 2 above.

**Two consequences that must travel with every future ENGU-Q figure.**
- **The sealed year no longer counts as evidence under the new rule.** It clears the 50-trade
  minimum, but strip its one 35-day hold and it loses $16,283, so it fails the profitability
  minimum outright. Quote the 47.4% only alongside that sentence, or not at all.
- **The 26.6% walk-forward number is an upper bound, not a forecast.** The walk-forward stretch of
  a continuous run is the crown's settings held FIXED across later years, not settings re-fitted
  fold by fold. The honest re-fitted read is the roll-corrected re-validate ENGU-Q #443, which
  returned 19.6% a year at stated size and graded WEAK. Plan on the lower number.

### 2026-09-28 - round 62, the cash-session entry window: FAILS its pre-registered bar, but it is the best entry result this family has produced

Pre-registered in `ENGUQ_R62_PREREG.md`, committed before a single cell was measured. Research
sibling `augur_strategies/ENGUQ_1M_ETH_R62_1_0.py`: the crown's file plus ONE gate - a signal is
only taken when the SIGNAL BAR's own timestamp falls inside a US Eastern clock window. Exits,
stops, trailing, the limit scan and the hold are untouched, so a trade entered at 15:55 still runs
for weeks. The window is folded into the per-bar boolean the parent already tests at the signal
bar, so the compiled and interpreted walks apply it identically.

**Why this is not the RTH branch that was already killed.** Runs #149 and #227 trade the
DAY-SESSION TAPE, where a genuine 24-hour resting stop costs the RTH champion $178,340. Round 62
keeps the 24-hour tape and the 24-hour stop exactly as the crown has them, and gates only the
entry signal. The night-trail-off file (`ENGUQ_1M_ETH_NF_1_0.py`, dead 2026-08-18) gated the
TRAIL at night, which is the opposite change. Neither result covers this one.

**The structural fact the round was built on.** On the paper cell, roll-corrected, whole window:
the 1,078 intraday deaths cost **-$493,422**, almost exactly the whole net of $493,295, while the
270 trades held longer than three days made **+$634,270**. Every dollar ENGU-Q has made comes from
trades that survive their first day. That is why capping the hold failed on 2026-09-27 - the cap
removes the edge - and why the lever is instead "stop paying for the trades that were never going
to survive".

**Result, one continuous run per cell on ADJ_NQ_1m_ETH, cost 0.783 x $20, drawdown valued daily:**

| | walk-forward | | | | sealed year | | | |
|---|---|---|---|---|---|---|---|---|
| | trades | ROC at $30k DD | Sortino | drawdown | trades | ROC at $30k DD | Sortino | without its biggest trade |
| raw twin, 24 hours | 1,178 | 26.8% | 3.66 | $48,566 | 116 | 44.4% | 3.38 | **-$16,283** |
| R62, 09:30-16:00 ET | 678 | **33.2%** | 3.59 | $35,170 | 67 | **62.6%** | **5.70** | **-$2,567** |

- **Clause 1, ROC at a $30k daily-valued drawdown, both stretches: PASS.** +6.4 points on the
  walk-forward, +18.2 points in the sealed year, on roughly half the trades and a 28% shallower
  walk-forward drawdown.
- **Clause 2, Sortino both stretches: FAIL.** The sealed year improves a lot (3.38 to 5.70) but
  the walk-forward slips from 3.66 to 3.59 - a 2% miss.
- **Clause 3, sample minimums: PASS** (678 walk-forward, 67 sealed).
- **Clause 4, sealed year survives losing its biggest trade: FAIL.** It loses $2,567 - six times
  better than the raw twin's -$16,283, and still the wrong side of zero.
- **Clause 5, era stability inside the engine: PASS.** Day-one survival for gated entries is
  38.9 / 36.4 / 38.8 / 37.5 percent across 2010-14, 2015-18, 2019-22 and 2023-26, against
  10.7 / 11.3 / 14.7 / 12.5 for the entries the gate removes. No drift in sixteen years.
- **Clause 6, harness gate: PASS.** With the window opened to 24 hours the file returns 2,053
  trades identical to `ENGUQ_1M_ETH_R2_1_0.py`, so every row above is a one-knob comparison.

**Verdict: no validate queued.** Two clauses of six fail. The bar was written before the numbers
and it does not move now, exactly as the round-57 daily-stretch cap was left dead on a 0.34-point
miss.

**The awkward part, stated rather than used.** The plateau, reported and never selected from:

| window (ET) | WF ROC at $30k | WF Sortino | LB ROC at $30k | LB Sortino | LB without its biggest |
|---|---|---|---|---|---|
| 09:00-16:00 | 31.4% | 3.41 | 56.1% | 5.06 | -$10,105 |
| **09:30-16:00 (pre-registered)** | 33.2% | 3.59 | 62.6% | 5.70 | -$2,567 |
| 10:00-16:00 | 27.3% | 3.14 | 50.6% | 4.92 | -$9,236 |
| 09:30-15:00 | 36.3% | 3.59 | 35.7% | 4.42 | -$22,966 |
| 09:30-16:30 | 33.5% | 3.60 | 58.4% | 4.98 | -$8,452 |
| 08:00-17:00 | 30.5% | 3.40 | 72.3% | 5.55 | **+$773** |

The one window that clears clause 4 is 08:00-17:00, which is NOT the window that was
pre-registered. Worse for the temptation: that window is also what a purely mechanical rule
selects - taking every hour whose median 1-minute volume is at or above the tape's own median
gives hours 08 through 16 ET exactly, computed from volume alone with no profit and loss involved
(median volume 130 to 935 inside it, 7 to 75 outside). **That is not a pass and it is not being
recorded as one.** The rule was written down after this table was read, so choosing it now would
be picking the bar after seeing the answer, which is the one thing this lane does not do.

**What this round actually establishes.** The liquidity mechanism is real and era-stable, and it
is the first ENGU-Q entry rule ever to improve the owner's yardstick in both stretches at once
while cutting drawdown - four earlier entry filters (round 57) failed at selection, and the whole
trend-gate, confirmation-gate, day-type and ML-gate families are closed. It also very nearly fixes
the family's central weakness: the sealed year's dependence on one 35-day hold falls from
-$16,283 to -$2,567 without capping a single trade.

**The one thing an owner must decide.** The clean way to settle the volume-defined window is on
data this round has not read - a fresh pre-registration graded on a stretch these tables do not
cover, or a forward paper shadow of the gated cell beside the live one. Re-grading it on this
window would not be evidence. My recommendation is the forward shadow: it costs nothing, it needs
no runner time, and it is the only reading that cannot be contaminated by what is written above.

### 2026-09-28 - the partial exit on the ETH crown: DEAD, 0 of 12 cells - an owed result, finally read

`augur_strategies/ENGUQ_1M_ETH_PX_1_0.py` and its bench `tools/enguq_px_bench.py` were built on
2026-09-05 with five bars pre-registered in both files, and then **never run to a published
verdict** - no result appears in this file, BACKTESTING_STACK.md, BOOKMARKS.md or the research
ledger. Run today exactly as it was written, against the #309 crown it was built for, so the bar
genuinely predates the numbers by three weeks. (The bench pointed at a 2026-09-05 worktree that no
longer exists; only that path was corrected, in a scratch copy. The committed tool is untouched.)

**Both parity anchors pass**, so every row below is a one-knob comparison: partial off reproduces
run #309 exactly (1,604 trades / $591,267 / PF 1.655) and the file's own defaults reproduce the
frozen #226 anchor to the cent ($434,721.12).

**The mechanism does precisely what it was meant to do, and it is still not worth it.** Banking
`partial_frac` of the position the first time open profit reaches `partial_R` times the initial
risk lifts the win rate from 33.7% to as high as 50.4%, drops the top-ten share from 57.7% to
44.0%, and cuts the drawdown from $48,900 to as little as $29,142. Every cell keeps a positive
net excluding its top ten, and every cell keeps at least 99 held-out trades.

**It fails on return per year, in all twelve cells, by a wide margin.** The bar allowed R per year
to fall 5%, from 43.4 to 41.23. The best cell manages 40.2 and the primary cell (partial_R 2.0,
partial_frac 0.5) manages 32.8 - a 24% give-up. Eleven of twelve also miss the MAR bar; the
single cell that clears MAR (partial_R 1.0 / frac 0.25 with breakeven 1.5, MAR 0.8811) gives up
30% of R per year to get there. **No cell passes all five bars.**

**Why it fails is the same sentence as round 62.** ENGU-Q's money is in the trades that survive:
the 270 holds longer than three days make more than the whole book's net, and the intraday deaths
cost almost exactly that net back. A partial exit takes size off a survivor at the moment it is
proving it will survive, so it always sells the good half of the distribution. The hold cap
(2026-09-27) failed for the same reason, and so does this. **Three separate mechanisms now agree:
nothing that reduces exposure to a winning ENGU-Q trade pays for itself.**

**Worth telling the owner, because it answers a question he asked on 2026-09-11.** He expected
ENGU-Q to show a high win rate at a modest profit factor and was surprised to find the opposite.
The partial exit produces exactly the picture he expected - a 49-50% win rate at profit factor
1.46-1.59 - and the price of that picture is about a third of the return. The shape he found
unintuitive is the shape that pays.

**No validate queued, and no port recommended.** Re-asking this on the current crown and the new
$30k-drawdown yardstick would cost about twenty minutes, but the failure mode is structural rather
than parameter-specific, so the answer is very unlikely to change. Recorded as DEAD; the file and
bench stay in the tree as the documented negative result they now are.

### 2026-09-30 - round 63, entry-bar order flow: NOT TESTABLE YET, and the checkpoint is about two years away

Pre-registered in `ENGUQ_R63_OFLOW_PREREG.md`, committed before a single order-flow number was
read. The idea, from the owner's 2026-09-30 ask: the family's money is entirely in trades that
survive their first day, so look for better survivors at entry - and the NinjaTrader 10-second
capture has carried `delta`, `buy_vol`, `sell_vol` and `tick_count` since late June without this
family ever using them. A breakout printed into genuine buying pressure should hold; one printed
into selling pressure should fail the same day.

**The sample was counted before the hypothesis was read, and it is far thinner than it looks.**
The capture spans 80 trading days, 2026-06-26 to 2026-09-30. Over that window the crown leg takes
33 trades. But only **22 of those 33 have any order flow at all**, and of those just **3 survived
day one** against 19 same-day deaths. The cash-session arm reads 4 and 13.

**Descriptive baseline, published because it was promised and not because it means anything.**
Median signal-window imbalance (the minute's delta over its volume, aggregated across the
parent's 10-bar limit scan): crown survivors +0.0266 against same-day deaths +0.0286, a gap of
**-0.0020** - i.e. nothing, on three survivors. The cash-session arm reads +0.0213 against
+0.0126, a gap of +0.0087, on four. Neither number is evidence of anything and neither may be
quoted as though it were.

**The finding that actually matters: the pre-registered checkpoint is not reachable soon.** The
bar is 60 survivors and 60 same-day deaths, read once. The crown leg produces day-one survivors at
roughly 36 a year, so 60 of them is about **twenty months away** - and that is before the capture's
own gaps, which are worse than expected: the median day holds 5,883 ten-second bars against the
~8,280 a full 23-hour session should give (71%), 25 of the 80 days hold under 2,000, and some are
nearly empty - 2026-08-27 has 42 bars, 2026-08-26 has 509. That hole is why a third of the crown's
trades have no order flow, including cash-session entries like 25 and 26 August. Routed to the
NinjaTrader paper lane, since the capture is theirs.

**What shipped instead of a verdict.** `tools/enguq_orderflow_ledger.py` records the entry-bar
order-flow reading for every ENGU-Q shadow trade into `C:\EdgeLog\enguq_orderflow\<LEG>.csv` -
survived-day-one flag, the raw volume, delta, buy, sell and tick parts, and the pre-registered
imbalance - keyed by entry time and safe to re-run. The sample now accumulates instead of being
re-argued from 33 points every month. It also surfaces the shadow's own warnings, because
`run_shadow` never raises and a missing master would otherwise read as a quiet "0 trades" - which
it did, once, on the first run from a worktree.

**Verdict: no result, no candidate, no validate, and the round stays open rather than being
closed either way.** Entry-bar order flow is neither supported nor refuted; it is unmeasured.

**Next in the queue, and it needs no owner decision.** The unit is the problem, not the idea. A
filled trade is a scarce event in this family, but a SIGNAL is not - every bar that clears the
entry filters is one, whether or not the resting limit fills it, and a signal's forward path
answers the same survivor question. Changing the unit changes the test, so it needs its own
pre-registration rather than an amendment to this one. That is round 64.

### 2026-09-30 - round 64, does entry-bar order flow carry ANY survivor information: NO, and the sign is backwards

Pre-registered in `ENGUQ_R64_OFLOW_POWER_PREREG.md` (commit 54e9e580) before a single number was
read. Round 63 could not test the order-flow idea at all - three day-one survivors, a checkpoint
twenty months out - so this round dropped the ENGU-Q signal requirement and asked what has to be
true underneath it: on this tape, does a bar's order-flow imbalance predict whether its move
persists to the next day?

**The obvious rescue was measured before being proposed, and abandoned.** Counting SIGNALS instead
of filled trades gives 2,766 against 2,053 over the full history - a 74% fill rate, 0.56 signals a
day against 0.41 trades. Eighty days of capture would yield about 44 signals rather than 33
trades. A 1.3x gain is not a rescue, so that round was never run.

**Population and result.** Every 1-minute upward breakout bar in the capture window - close above
its open and above the previous bar's high, no other filter - that has a forward path one session
later: **12,972 bars**, with 4,629 more (26%) excluded because their minute carries no order flow,
the capture hole already routed to the NinjaTrader lane.

| cut | n | bottom imbalance quintile persists | top quintile persists | gap | p |
|---|---|---|---|---|---|
| all breakout bars | 12,972 | 50.5% | 47.7% | **-2.9 pts** | 0.040 |
| narrow range | 4,324 | 48.4% | 47.5% | -0.9 | 0.70 |
| middle range | 4,324 | 49.8% | 47.3% | -2.4 | 0.31 |
| wide range | 4,324 | 55.2% | 49.5% | -5.7 | 0.018 |
| cash session only | 3,825 | 50.2% | 44.8% | -5.4 | 0.036 |

**Both clauses fail.** The bar was a 10-point gap at p below 0.01, surviving in the majority of
range terciles. The largest gap anywhere is 5.7 points, no tercile clears, and every p is above
0.01. **Verdict: entry-bar order flow carries no usable survivor information on this tape.**

**The interesting part is the sign, and it is not a new hypothesis.** Every cut is NEGATIVE: bars
printed into the heaviest buying persist LESS often, most visibly in wide-range bars and inside
the cash session. That is the opposite of the mechanism proposed in round 63, and it reads like
absorption rather than continuation - heavy buying into a breakout that then goes nowhere. It is
recorded because it is what the data says, **not** as a reversed filter to go and build: choosing
that hypothesis now, after seeing this table, is exactly the move this lane does not make. Any
reversed rule needs its own pre-registration on data this round has not read, and at gaps under
the 10-point floor on 13,000 bars it is not worth the runner time.

**Consequences.** The round-63 ledger (`tools/enguq_orderflow_ledger.py`) keeps accruing, because
it costs nothing and the data is now being banked either way, but nobody should wait twenty months
for its checkpoint expecting a result - the high-powered version of the question has already
answered it. Entry-bar order flow joins the dead-hunt list for this family: tested, not merely
untested.

**Caveats that would matter if this had passed.** Consecutive breakout bars share almost all of
their forward path, so the effective sample is far below 12,972 and the p-values are optimistic -
which only strengthens a failure. The window is one regime, three months. And 26% of the
population was dropped for missing order flow, so if that hole correlates with time of day the
survivors are not a random subset.

### 2026-09-30 - round 65, distance below the recent high: the survival effect is REAL and era-stable, and it is worth nothing

Pre-registered in `ENGUQ_R65_PREREG.md` (commit 18ca3aee) before any survival or profit number was
read. Research sibling `augur_strategies/ENGUQ_1M_ETH_R65_1_0.py`: the crown's file plus one entry
test - the signal close must sit within `max_room_atr` ATRs of the highest high of the previous
1,380 bars. Exits, stops, trailing and the hold are untouched.

**The round's first result cost nothing and killed the idea it started as.** It began as OVERHEAD
SUPPLY - require room above the entry so the trade is not breaking into a nearby prior high. Dead
at the design stage, before any outcome was read: over the crown's 2,053 entries the distance up
to the previous session's high has a median of **12.5 ATR** and a lower quartile of 6.95, while
the trade needs about 2.5 ATR to activate its trail. There is no overhead-supply problem here to
filter. What that showed instead is that **ENGU-Q enters about twelve ATR BELOW recent structure**
- it buys a bounce inside a decline, not a breakout into clear air - so the hypothesis was
reversed: entries NEAR the prior high should be the survivors.

**And they are. Clause 5 passes cleanly, in every era:**

| era | kept entries survive day one | removed entries |
|---|---|---|
| 2010-14 | 33.9% (n=286) | 19.8% (n=379) |
| 2015-18 | 32.1% (n=346) | 16.1% (n=385) |
| 2019-22 | 31.2% (n=349) | 19.0% (n=363) |
| 2023-26 | 30.1% (n=269) | 18.9% (n=281) |

A 12-to-16 point separation, stable across sixteen years with no drift. The mechanism is real.

**It is also worth nothing, and three clauses fail.** Against the raw twin on ADJ_NQ_1m_ETH with
the drawdown valued daily: walk-forward ROC at a $30k drawdown falls **26.8% to 22.8%** (clause 1
fails), walk-forward Sortino 3.66 to 3.65 (clause 2 fails), and the sealed year without its
biggest trade gets **worse**, -$16,283 to -$18,746 (clause 4 fails). Samples are fine (741 and
74) and the harness gate passes - the filter off reproduces the parent's 2,053 trades exactly.
The sealed stretch does improve (ROC 44.4 to 55.1, Sortino 3.38 to 3.90), but one stretch is not
the bar. **Verdict: no validate queued.** The plateau at 4 / 6 / 12 / 16 ATR is reported in the
harness output and not selected from; no threshold clears clause 1.

**Why it is worth nothing, measured rather than guessed.** The filter removes 39% of all trades
(2,053 to 1,250) and the sealed net barely moves: **$74,869 to $72,708**. It keeps the one 7 April
hold that IS the sealed year ($91,152, still 126% of the total afterwards) and strips out trades
whose aggregate contribution is close to zero. Concentration hardly improves - the sealed top-ten
share goes 226% to 201%.

**The family lesson, now from two independent filters.** Round 62's cash-session gate and round
65's room filter both separate day-one survivors by 12-25 points, era-stably, and **neither
converts that into ROC**. The reason is now explicit: surviving day one is far too common a
property to be the thing worth selecting. About a quarter of all entries survive, the money is in
a handful of long holds, and a filter that doubles the survival rate still keeps hundreds of
mediocre survivors and removes hundreds of near-free losers. **"Find better survivors" is the
right instinct and the wrong target** - day-one survival is a diagnostic of what pays, not a
selectable proxy for it. Anything future rounds propose should be aimed at the long holds
specifically, and should be able to say in advance why it would keep the 35-day trade while
dropping the ordinary survivors, not merely lift the survival rate.

### 2026-09-30 - adversarial audit of the 09-29/30 builds: three real defects fixed, two numbers restated

Owner ask through the MANAGER chat: re-check the new builds for errors. An adversarial read-only
audit was run over the round-62 session-window file, the two shadow paper legs and the round-63
order-flow ledger, with every claim executed rather than inferred. Ten findings; the three that
mattered are fixed below, and the ones that changed a published number are restated. Clean on the
things that would have been worst: no look-ahead, exact parent parity, correct dtype through the
compiled walk, and both shadow arms genuinely fenced off from every order path.

**DEFECT 1, and it was a leak against this lane's own rule.** The ledger aggregated the ten
minutes *ending at and including the fill minute*. The parent rests its limit and scans forward
one to ten bars, so the signal is in `[fill-10, fill-1]` and the fill bar is never the signal bar
- which means the window both omitted a legitimate signal minute and **included the fill minute,
the exact fill-bar read the round-63 pre-registration forbids**. Fixed to the parent's scan
window.

**DEFECT 2: the ten-second rows are stamped at the bar's END.** The ledger bucketed by
`t - (t % 60)`; the house rule, in `api/paper.py::_resample` and `tools/backfill_1m_from_10s.py`
alike, is `(t - 1) // 60`, and a missing `-1` once put 11,611 of 12,762 minute opens at odds with
the Databento master. Every minute was stealing the previous minute's last ten seconds. Fixed.

**DEFECT 1b, found by MANAGER's independent review and worse than the above: the predictor was
never the one that was pre-registered.** The pre-registration names "the SIGNAL bar's order-flow
imbalance ... the minute's delta divided by its volume" - ONE minute. The ledger recorded a
ten-minute aggregate, and the trade time it started from is the FILL bar, so on a tenth-bar fill
the window contained no signal minute at all. Fixing the window to [fill-10, fill-1] removed the
leak but still did not compute the pre-registered quantity.

**The true signal bar is recoverable exactly, and now is.** The parent rests its limit at
`close - limit_atr x ATR` on the signal bar, and that resting price IS the recorded entry price,
so rebuilding the parent's own ATR and walking back up to ten bars identifies the signal bar to
within a quarter tick. It resolved **100% of trades on the first run, 0 unidentified**. The
single signal minute is now the PRIMARY column and the only one the checkpoint may read; the
ten-minute window and the fill minute are kept as clearly-labelled descriptive columns. The fill
minute especially must never be used - a resting limit buy is by construction hit by sellers, and
its imbalance averages about -0.05 against the window's +0.04.

**Restated on the correct predictor, crown leg, 22 trades scored:** median signal-minute imbalance
**+0.0499** for trades held 24 hours or more against **+0.0856** for the rest, a gap of
**-0.0357** - where the original cut printed -0.0020 on the wrong quantity. The cash-session arm
reads +0.0517 against +0.0852, a gap of -0.0335. **None of this changes round 63's conclusion**,
which was that three survivors cannot test anything; and the sign agrees with round 64's
independent finding that heavier buying goes with worse persistence.

**DEFECT 1c, same review: an OPEN trade was being counted as a same-day death.** An open position's
exit is stamped at the last bar, so anything younger than 24 hours scored as a death - a bias
against every fresh entry, which would have grown as the ledger accrued. Such rows are now written
as `unresolved` and excluded from the comparison; one row on the current run.

**Round 64 was re-run on the corrected stamping and its verdict stands.** 13,119 upward breakout
bars instead of 12,972; top imbalance quintile persists **49.4%** against the bottom's **51.9%**,
a gap of **-2.5 points** (was -2.9) at p 0.068, and no range tercile clears - widest -6.1, cash
session -5.9, middle +0.8. Both clauses still fail and the sign is still negative nearly
everywhere. Entry-bar order flow stays dead.

**DEFECT 3: the declared search grid could not reach the cells we actually run.** The optimiser
walks an integer knob as `min + step*k`. With `sess_to` declared min 800 step 30, the value 1600 -
the pre-registered arm's own window - is **off the lattice**, as are S2's 0800 and the 2400 that
the docstring calls the parity anchor. An Auto-Validate of this file could never have evaluated
the cell it was validating. Both knobs are now step 10 from 0, which puts 0, 800, 930, 1600, 1700
and 2400 on the grid. This was caught by the new test below, not by eye.

**The definition of "survived day one" is now pinned, because two reasonable readings disagree in
opposite directions on exactly the entries the cash-session gate removes.** Elapsed time of 24
hours or more is PRIMARY and is what the family's whole-history hold table already uses; it is
entry-time neutral. The calendar-date reading - exit falls on a later date - is entry-time BIASED,
because a 23:00 entry exiting at 01:00 held two hours and would score as a survivor. On the
current 33-trade sample the two give a +16.7 point gated-versus-removed gap and a 0.0 point gap
respectively, which is exactly why it is pinned now rather than at the checkpoint. The ledger
writes both columns plus the raw hold in hours, so no later reader inherits the choice blind.
`ENGUQ_R62_FORWARD_PREREG.md` clause 1 is clarified to name the elapsed-24-hour reading; the
15-point bar itself is unchanged.

**Latent defects fixed while in there.** A naive bar index was assumed to be UTC, which silently
shifted the window four to five hours and was not DST-stable - every other strategy here that
localises a naive index treats it as Eastern, so this one now does too, and a wrong-length index
raises instead of being read out of bounds by a compiled walk that carries no bounds checking.
The parity the docstring claimed was "asserted by the round's own harness" had no harness;
`tests/test_enguq_r62_parity.py` now locks down trade-for-trade parity with the parent when the
window is off, compiled-versus-interpreted agreement when it is on, both refusals, and the grid
reachability that caught defect 3. The file's description string, which is what the strategy
picker shows, still described the parent; it now describes the window.

**What was clean, stated because it is worth knowing.** The gate reads `er_ok` at the signal bar
and nowhere else, in both the interpreted and compiled paths, at the same index. With the window
open the file returns the parent's trade list exactly. The boolean fold cannot become a float. And
the two shadow arms carry the crown's fourteen knobs with nothing drifting, take their `live_from`
through the same mechanism as every other leg, and cannot reach NinjaTrader, the cloud signal path
or the live gate - each checked by hand.

### 2026-10-02 - round 66, initial risk width as the long-hold selector: FAILS, and it closes the entry-filter direction

Pre-registered in `ENGUQ_R66_PREREG.md` (commit 156c29c8) before any hold length, survival rate or
profit number was read. Research sibling `augur_strategies/ENGUQ_1M_ETH_R66_1_0.py`: the crown's
file plus one entry test - the entry-to-swing-low distance must be at least `min_risk_atr` ATRs.
Exits untouched.

**This round answered the condition MANAGER set after round 65** - say in advance why a rule keeps
the 35-day trade and drops ordinary survivors - with an argument from the exit rule rather than
from data. The trail rides `trail_frac x risk` below the running high, fixed in points at entry.
A trade therefore lives exactly as long as the market never retraces that distance, retracements
scale with volatility, so survivable days increase with `risk / ATR` at the signal bar. The
inverse experiment supported it: capping initial risk (`ENGUQ_1M_RC_1_0`) destroyed the edge,
$453,532 down to -$75,905, and was written up as "ENGU-Q's profit LIVES in the wide stop".

**Result against the raw twin, ADJ_NQ_1m_ETH, drawdown valued daily:**

| | WF trades | WF ROC at $30k | WF Sortino | LB trades | LB ROC at $30k | LB Sortino | LB without its biggest |
|---|---|---|---|---|---|---|---|
| raw twin | 1,178 | 26.8% | 3.66 | 116 | 44.4% | 3.38 | -$16,283 |
| risk >= 8.83 ATR | 960 | 26.5% | 3.06 | 85 | **59.1%** | **4.27** | **+$614** |

**Clause 4 passes for the first time in this family's history.** No ENGU-Q variant has previously
produced a sealed year that stays profitable without its single biggest trade. That is the clause
the live cell fails at -$16,283, and the one the owner's yardstick cares most about.

**And three clauses still fail, so no validate is queued.** Walk-forward ROC is flat to slightly
down (26.5 against 26.8), walk-forward Sortino drops hard (3.06 against 3.66), and the mechanism
clause fails in two of four eras - the share of trades held longer than three days among kept
entries against removed ones runs 1.49x, 1.42x, 2.24x and 1.67x against a required 1.5x. One of
those misses is by 0.01. **The bar does not move**: round 57's stretch cap was left dead on a
0.34-point miss and round 62 on a 0.07 Sortino miss.

**The plateau is why the +$614 should not be rescued, and this is the most useful thing in the
round.** Reported and not selected from: at 7.12 ATR the sealed year without its biggest trade is
-$22,468; at 8.83 it is +$614; at 11.53 it is -$20,652; at 15.02 it is -$17,140. **The result is
not monotone in the threshold.** If the stated mechanism were driving it, a wider minimum risk
would mean a wider trail would mean a steadier improvement. Instead a single interior point is
positive and both neighbours are deeply negative, which is the signature of which particular
trades happened to survive, not of the mechanism working. Walk-forward ROC tells the same story -
28.1, 26.5, 15.5, 13.2 - it falls apart as the filter tightens.

**The direction is now closed, and that is the round's real output.** Counting round 57's four
pre-registered entry rules plus rounds 62, 65 and 66, **seven entry filters have now been tested
against a bar written in advance and all seven have failed** - every one of them on the
walk-forward stretch, and every one of them after demonstrating a real, era-stable mechanism
first. Cash-session timing separates day-one survivors by 25 points; distance below the recent
high separates them by 12 to 16; risk width separates three-day holds by 1.4x to 2.2x. None of
it converts. **The conclusion is that ENGU-Q's entry is not improvable by declining signals.**
The refill effect is the mechanical reason - a declined signal frees the slot and the walk takes
a later, worse signal of the same move - and it has now beaten three different true mechanisms.

**What this lane should stop doing, and what is left.** Stop proposing entry filters; the prior
is now seven failures deep and the next one needs an argument for why it escapes the refill
effect, not merely a mechanism. What remains untried and is not a filter: changing what the
strategy does with a signal it has already taken, without reducing exposure to winners - which
rules out the hold cap, the partial exit and risk caps, all already dead. That is a narrow gap,
and it may be empty. The honest position is that ENGU-Q #335 is a finished strategy and the
lane's remaining value is in guarding it, not improving it.

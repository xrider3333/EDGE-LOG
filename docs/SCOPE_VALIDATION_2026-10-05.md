# SCOPE: the validation frontier - how the house judges, selects and watches (FRONTIER cloud lane, 2026-10-05)

Owner standing-order addendum 2 (2026-10-05 12:45 MST, "push and scope out deeply this time"): every lane writes a scoping
document - 10 to 20 mechanisms from the literature for its domain, the data each needs, a dead-list cross-check, map placement,
ranked order - then works it as a queue that never drops below three live pre-registrations. The local FRONTIER lane scopes the
BOOK itself (leg mix, stock baskets as the seat class, stock-event families); this lane's domain since 10-03 has been the
program's VALIDATION (RISK r1, LOOKS r1, GUARD r1, XGAP r1): how a candidate is judged, how a pass is known from luck, and how the
adopted book is watched. Nothing below has run. Each item becomes its own pre-registration, reviewed by MANAGER, before any
number. This doc is not a pre-registration.

## 0. Where the program stands, and why the validation side is now the frontier

Three findings this week are properties of the TESTS, not of any strategy:

- **The lockbox year is spent.** After 71 printed looks, a no-edge book candidate clears the lockbox clause 42% of the time as a
  seat change and 24% as a sizing rule; no margin up to double rescues it (LOOKS r1, BOOK.md 10u; ledger 2.57).
- **The forward reads cannot decide.** As registered, a 12-month read passes at least one of six no-edge lines 89% of the time; a
  fair bar needs margins no line reaches, because four of the six lines earn no more money than #463 - their gain is a smaller
  drawdown, which a mean-type read cannot see (Q16, 10y; ledger 2.65).
- **The walk-forward gains are inside chance.** Every line's walk-forward gain sits inside what 71 looks produce by luck (Q17,
  10z; ledger 2.66), and Q18 confirmed the band's width on the walk-forward (ratio 1.18).

The owner ruled on all three on 2026-10-05 (BOOK.md 10aa): #463 stays; the walk-forward selects with the chance band printed; no
candidate is passed on the spent lockbox; forward lines are harm monitors; adoption is the owner's call on walk-forward plus
mechanism. Every candidate tried since (Q9, Q12, Q13, Q15, SIPORB, ATTN, DDW, XGAP) died at Stage A. So the rate at which the
frontier can move is now set by the measuring instruments: how much evidence a year of forward data yields, how many looks the
next sealed year can absorb, and whether the adopted book itself is watched. That is this lane's scope.

**The map (MDL r1, docs/MDL_MAP_R1.md), restated for tests rather than legs.** A candidate change to #463 is one of three kinds:
(i) more money at the same drawdown (NOISE x1.25, KEEL): readable on dollars, slowly; (ii) the same money at a smaller drawdown
(ORB314, ORB239, Q4, VT): invisible to every mean-type read, because a drawdown difference is one episode; (iii) a new leg with
zero index beta (every stock family so far): dead on costs. Kind (ii) is where every surviving line sits, and no registered read
can see it. Items 1 and 2 below are built for exactly that.

## 1. The ranked list

Columns: what it is; the literature; what it needs; dead-list cross-check (what the house already ran or owns); map placement
(which decision it informs); status.

| # | Mechanism | Literature | Needs | Dead-list cross-check | Map placement | Rank / status |
|---|---|---|---|---|---|---|
| 1 | **BOOK HEALTH r1** - a daily monitor of the ADOPTED book against its own walk-forward: a one-sided CUSUM on standardised daily P&L (decay), the current drawdown against the backtest's drawdown distribution for the same record length, per-leg firing rates; thresholds from a block bootstrap of the walk-forward at a fixed false-alarm rate; a power table that says how many days a vanished edge takes to show | Page (1954) CUSUM; Lorden (1971); Bailey & Lopez de Prado (2012) minimum track record; the house's own P95-drawdown convention | r11's records (exists); the paper `book` line as a daily CSV on the restated basis (owner decision a, PAPER-NT8) | GUARD r1 checks the record's INTEGRITY, not its performance; the paired stops and shadow reads judge candidates vs #463, never #463 vs its backtest. **Nothing watches the adopted book.** | The adopted book itself: when to reduce size, pause a leg, re-validate | **1 - prereg written** (`tools/rocfrontier/PREREG_HEALTH_R1.txt`, harness r18_health.py) |
| 2 | **MATCHED READ r1** - for the lines whose gain is a smaller drawdown (ORB314, ORB239) and for KEEL, a forward statistic matched to the mechanism: the paired downside-deviation ratio of the changed leg vs #463's leg on the same days (Sortino's own denominator), loss-day gain and tail quantile as secondaries; power at 12 / 24 / 36 months from Q16's machinery with a within-pair swap null; family-wise 5% over the three lines | Ledoit & Wolf (2008) robust paired performance tests; Good (2005) permutation tests for paired scale; Q16's joint block bootstrap | Q16's rebuilt walk-forward series + the ORB #314 / #239 leg caches + KEEL's paired d_i (all on the box; exported as one manifest CSV) | Q16 tested mean-type rules only (ROC margin, dollars) and found 1-7% power on these lines; the paired-stop prereg pairs on the MEAN; VT (RISK r1 dead) and Q4 (post-hoc) excluded by rule | The forward lines: whether any kind-(ii) line can ever be DECIDED rather than only watched for harm | **2 - prereg written** (`tools/rocfrontier/PREREG_MATCHED_R1.txt`, harness r17_matched.py) |
| 3 | **Anytime-valid monitors** - replace the fixed-look paired stops (looks at trades 20, 30, ...; boundary B tuned by redraws) with confidence sequences / e-processes that stay valid at EVERY look with no penalty for looking, so a line can be read daily and stopped the day the evidence is there | Howard, Ramdas, McAuliffe & Sekhon (2021) time-uniform confidence sequences; Waudby-Smith & Ramdas (2023) betting e-processes; Ramdas, Grunwald, Vovk & Shafer (2023) safe anytime-valid inference | The per-trade paper records (exist); no new data | The house's paired stops are the fixed-look version (docs/PREREG_paired_sequential_stop_2026-09-29.md); HEALTH r1's bootstrap-calibrated CUSUM serves the same end for the adopted book | Every forward line and the adopted book: continuous reading with a known error rate | 3 - after 1 and 2 (an r2 of the paired stops, co-owned with Custom ML who froze the constants) |
| 4 | **A reusable holdout for the NEXT sealed year** - when the masters pass 2027-06-30 the year 2026-07..2027-06 becomes a new lockbox; before the first look, adopt the Ladder: a candidate's sealed figure is never printed, only "clears the current bar by at least one step" (a step = the noise level), and the board moves only on a step; with Thresholdout's noise this bounds how much a year can be overfitted by many looks | Blum & Hardt (2015) The Ladder; Dwork, Feldman, Hardt, Pitassi, Reingold & Roth (2015) The reusable holdout; RESEARCH.md items 1 and 4 (looks counter) | An engine / web rule (ELwA's engine scoping: a sealed read that returns pass / fail only) and a MANAGER house line | LOOKS r1 counted the looks after the fact; RESEARCH.md item 4 proposed a counter; neither stops a look from spending the year. Nothing of this kind exists | The next lockbox: how many candidates one sealed year can judge before it is spent (today: about ten) | 4 - spec in section 2 below; an owner decision via MANAGER, engine work by ELwA; not a prereg from this lane |
| 5 | **Joint multiple testing over the looks** - White's Reality Check / Hansen's SPA / Romano-Wolf stepdown over every look's daily difference series, so the chance band uses the looks' real correlation instead of treating 71 looks as independent | White (2000); Hansen (2005); Romano & Wolf (2005); Westfall & Young (1993) | Each look's daily difference series: recoverable for the #463-era looks (about 22 of 71: Q1-Q6, round 62, AG, P1 / P2, MDL rows, #468-#470); the 49 pre-#463 looks were against #397 / #436 / #456 and most have no daily series on disk | tools/reality_check.py runs White's RC over a validate's TEN FINALISTS (RESEARCH.md item 3) - a different question; Q17 used the independent band; Q16 kept cross-line correlation for the six lines only | The walk-forward selection band for every future candidate | 5 - honest expectation: a modest narrowing (correlation shrinks the effective K, but the 49 unrecoverable looks must stay Bonferroni); worth one cheap round only if MANAGER wants the band exact |
| 6 | **The multiple-testing hurdle for new legs** - raise Stage A's t >= 2 to the hurdle the literature puts on a new effect judged among many: t >= 3, or the per-family false-discovery control of Harvey & Liu | Harvey, Liu & Zhu (2016); Harvey & Liu (2020) false (and missed) discoveries | Nothing: a number in every Stage A prereg | Every stock family this week (SIPORB, ATTN, DDW, XGAP) died below t 2 anyway; the hurdle would have changed no verdict yet | Stage A of every new leg | 6 - a house line for MANAGER, not a round |
| 7 | **Minimum track record length on the adoption page** - for each forward line, the months of forward data its own walk-forward Sortino needs before a pass could be trusted, printed beside the chance band and Q16's months | Bailey & Lopez de Prado (2012) | Each line's paired daily difference (in item 2's manifest) | RESEARCH.md item 4 ("months until trustworthy") proposed it for crowns; never computed for the book lines | The adoption page: one more honest number per line | 7 - folded into MATCHED r1's report (one line per line, report only) |
| 8 | **A registered regime-concentration clause** - no single 63-day block may hold more than half of a candidate's walk-forward gain; what A4 and "without Feb-Apr 2020" do by hand, as a rule in every book prereg | Harvey (2017) presidential address (fragility of effects); the house's own 10v-10x findings | Nothing | Q9 / Q12 / Q13 / Q15 each died on exactly this, each by a hand check | Every book candidate's Stage A | 8 - a house line for MANAGER |
| 9 | **Cross-market sign replication as independent out-of-sample** - a candidate change counts as evidence only if its SIGN replicates on markets it was not tuned on (QQQ / SPY / IWM / sector funds at 5 minutes, which the ORB and NOISE lanes are now scoping and MANAGER pulls) | Baltussen, Swinkels & van Vliet (2021) global factor premiums; Harvey (2017); Jensen, Kelly & Pedersen (2023) replication | The Alpaca 5-minute fund pulls (in flight for the ORB / NOISE scoping) | TRANSFER r2 (ledger 2.49): the crowns' edges do NOT carry to bond / gold funds and are flat on DIA / IWM - replication is a hard bar, which is the point; TRANSFER r1 shelved (owner declined Databento) | What a walk-forward pass is worth: a sign that repeats on four markets is evidence the spent lockbox cannot give | 9 - a rule proposal for the ORB / NOISE fund rounds (pre-register the sign test across >= 4 markets, not one market at a time); not a prereg from this lane |
| 10 | **Combinatorial purged cross-validation for book changes** - many walk-forward paths instead of one, giving a distribution of out-of-sample gains for a book change rather than a single number, with purging at every cut | Lopez de Prado (2018) ch. 12; RESEARCH.md item 12 | Engine work (items 2 and 7 of RESEARCH.md first) | PARKED in RESEARCH.md as large; the single-strategy validate has PBO already | The walk-forward selection step | 10 - parked until the engine items ship |
| 11 | **Capital on a line while it is being read** - how much to trade a shadow line before it is decided: a fractional-Kelly ladder under parameter uncertainty, paper -> micro -> full | Baker & McHale (2013) optimal betting under parameter uncertainty; Carver (2015) | The forward records; an owner-facing rule | None (no line has any capital today) | The owner's live decision, after the first decided line | 11 - later, owner-facing |
| 12 | **Empirical-Bayes shrinkage of candidate gains** - shrink each candidate's walk-forward gain toward the family's prior measured from the 71 looks themselves | Harvey & Liu (2020); Efron (2010) | The looks ledger (exists) | Q18 calibrated the chance band against the ten real one-change reads (ratio 1.18) - the same correction, done | Adoption page | 12 - done in substance by Q18; dead-list |
| 13 | **Synthetic histories** (regime-mixing, GAN / diffusion generators) to stress a candidate beyond the one realised path | various | New code; no data | The house's block bootstrap answers every question asked so far; a generator adds assumptions, not evidence | - | 13 - not pursued; listed so it is not re-proposed |
| 14 | **Live-fill parity** - when live money follows a line, the live fills vs the paper fills vs the backtest's cost model, as GUARD r2 | house GUARD r1 | A live record (none yet) | GUARD r1 covers paper vs cold engine only | The first live line | 14 - PAPER-NT8's, when live trading starts |

## 2. Item 4 spelled out: a sealed year that does not get spent

What spent the 2025-26 year was not the number of candidates but the PRINTED FIGURE: every look returned the candidate's exact
lockbox ROC, which every later candidate was then tuned against (knowingly or not). The literature's answer is two rules that
cost nothing in engine time:

- **The Ladder (Blum & Hardt 2015).** The sealed read returns one bit - "beats the current bar by at least one step" - and the
  bar moves only when a candidate clears it by that step; the step is the sealed year's own noise level (LOOKS r1 measured it:
  about 8.6% in log ratio for one-change reads; the step would be one such spread). Blum and Hardt prove the leaderboard then
  overfits only logarithmically in the number of looks instead of linearly.
- **Thresholdout (Dwork et al. 2015).** Where a figure must be returned, return it only when the training (walk-forward) and
  holdout (sealed) figures differ by more than a threshold, and add Laplace noise at the step size; otherwise return the
  walk-forward figure. With n = 252 daily rows the formal guarantee is weak (the bounds are asymptotic in n), so the house rule
  would rest on the Ladder, with Thresholdout's noise as the second lock.

What it needs: the engine's sealed read (validate's lockbox stage) gains a mode that prints pass / fail against a stored bar and a
step, never the figure; the RUNBOARD shows the bit; the figure is written to a file nobody reads until the year is retired. ELwA's
engine scoping doc owns the job; MANAGER owns the house line; the owner decides whether the next sealed year starts under it.
This lane will write the rule as a pre-registration (what the bar is, what a step is, who may read the file) on MANAGER's word.

## 3. The queue this lane proposes (three live pre-registrations)

1. **BOOK HEALTH r1** - `tools/rocfrontier/PREREG_HEALTH_R1.txt`, harness `r18_health.py` (calibrate / read / smoke), tests. Minutes on
   the box from r11's cache; the daily read needs the paper lane's CSV of the `book` line on the restated basis. First useful
   output BEFORE any forward row: the power table (how many days a vanished edge takes to show).
2. **MATCHED READ r1** - `tools/rocfrontier/PREREG_MATCHED_R1.txt`, harness `r17_matched.py` (parity / run / smoke), tests. Minutes on
   the box from Q16's rebuilt series and the ORB / KEEL caches, exported as one manifest CSV by the local FRONTIER lane. Output: per
   line, the months at which a matched read reaches power 0.5 / 0.8, beside Q16's "> 36".
3. **GUARD r1** (already live, monthly; first binding read 2026-10-30) stays the third. The ladder rule (item 4) is written as the
   fourth when MANAGER says so.

Recommendation on order: HEALTH first (it protects the adopted book and needs nothing new), MATCHED second (it is the only path by
which a kind-(ii) line can ever be decided), the Ladder rule before the next sealed year opens.

## 4. Dead-list the house already holds (so none of it is re-proposed)

Kronos Step 0 (dead, 2.54), V3 learned risk forecast (FAIL at the forecast gate, 10s), RISK r1 (V2 vol target = two lucky drawdowns,
2.47), LOOKS r1 (the lockbox is spent, 2.57), Q16 (forward reads cannot decide, 2.65), Q17 / Q18 (walk-forward gains inside chance;
band width confirmed, 2.66), MDL r1 (the map, 2.51), TRANSFER r1 shelved / r2 dead (2.29, 2.49), every stock family (SIPORB 2.60,
ATTN 2.61, DDW 2.62, XGAP 2.63), every crisis seat (Q9 2.58, Q12 / Q13 2.59, Q15 2.64), the ML gates (10l: the ML legs add nothing in
the book), re-weighting (round 56: no forward skill), tools/reality_check.py (White's RC over a validate's finalists, RESEARCH.md
item 3: weak at eight folds).

## 5. Sources (checked against the text where a figure is quoted; pointers otherwise)

- Page, E. S. (1954). Continuous inspection schemes. Biometrika 41, 100-115.
- Lorden, G. (1971). Procedures for reacting to a change in distribution. Annals of Mathematical Statistics 42, 1897-1908.
- Bailey, D. H. & Lopez de Prado, M. (2012). The Sharpe ratio efficient frontier. Journal of Risk 15(2), 3-44 (minimum track record length).
- Ledoit, O. & Wolf, M. (2008). Robust performance hypothesis testing with the Sharpe ratio. Journal of Empirical Finance 15, 850-859.
- Good, P. (2005). Permutation, Parametric and Bootstrap Tests of Hypotheses, 3rd ed., Springer.
- Howard, S. R., Ramdas, A., McAuliffe, J. & Sekhon, J. (2021). Time-uniform, nonparametric, nonasymptotic confidence sequences. Annals of Statistics 49(2), 1055-1080.
- Waudby-Smith, I. & Ramdas, A. (2023). Estimating means of bounded random variables by betting. JRSS-B 86(1), 1-27.
- Ramdas, A., Grunwald, P., Vovk, V. & Shafer, G. (2023). Game-theoretic statistics and safe anytime-valid inference. Statistical Science 38(4), 576-601.
- Blum, A. & Hardt, M. (2015). The Ladder: a reliable leaderboard for machine learning competitions. ICML 2015.
- Dwork, C., Feldman, V., Hardt, M., Pitassi, T., Reingold, O. & Roth, A. (2015). The reusable holdout. Science 349(6248), 636-638.
- White, H. (2000). A reality check for data snooping. Econometrica 68(5), 1097-1126.
- Hansen, P. R. (2005). A test for superior predictive ability. Journal of Business & Economic Statistics 23(4), 365-380.
- Romano, J. P. & Wolf, M. (2005). Stepwise multiple testing as formalized data snooping. Econometrica 73(4), 1237-1282.
- Westfall, P. H. & Young, S. S. (1993). Resampling-Based Multiple Testing. Wiley.
- Harvey, C. R., Liu, Y. & Zhu, H. (2016). ... and the cross-section of expected returns. RFS 29(1), 5-68.
- Harvey, C. R. & Liu, Y. (2020). False (and missed) discoveries in financial economics. Journal of Finance 75(5), 2503-2553.
- Harvey, C. R. (2017). Presidential address: the scientific outlook in financial economics. Journal of Finance 72(4), 1399-1440.
- Baltussen, G., Swinkels, L. & van Vliet, P. (2021). Global factor premiums. Journal of Financial Economics 142(3), 1128-1154.
- Jensen, T. I., Kelly, B. & Pedersen, L. H. (2023). Is there a replication crisis in finance? Journal of Finance 78(5), 2465-2518.
- Lopez de Prado, M. (2018). Advances in Financial Machine Learning. Wiley, ch. 12.
- Baker, R. D. & McHale, I. G. (2013). Optimal betting under parameter uncertainty: improving the Kelly criterion. Decision Analysis 10(3), 189-199.
- Efron, B. (2010). Large-Scale Inference. Cambridge University Press.
- Carver, R. (2015). Systematic Trading. Harriman House.

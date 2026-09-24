# RESEARCH LEDGER — what has been tried or added, and where the evidence lives

One row per line of work, with the document that holds its evidence and the verdict it earned.
Owner asked for this on 2026-09-23. It is an INDEX, not a summary: every claim below is written
out in full in the source document named beside it.

Three kinds of row, kept apart on purpose:
- **Section 1 — how we VALIDATE.** Changes to the machine that judges a strategy.
- **Section 2 — what we SEARCHED for.** Attempts to find new edge. Almost all are nulls; they are
  listed so nobody pays for them twice.
- **Section 3 — tools.** The drivers that produced the evidence, so any row can be re-run.

Money note: NQ figures in points are multiplied by $20 where dollars are quoted. Never compare
eras in raw dollars — NQ's amplitude grew about seven-fold over the window.

---

## 1. Validation methodology

| # | Tried / added | Source document | Outcome |
|---|---|---|---|
| 1.1 | Which reading predicts the held-out year: fixed-settings walk-forward vs re-tuned walk-forward vs lockbox | `docs/WF_LOCKBOX_DEEP_DIVE.md` | The fixed walk-forward column is the score the crown was SELECTED on (~16% above the honest reading), the re-tuned test is calibrated (lockbox PF ÷ reading PF median 0.99), the lockbox cannot rank anything |
| 1.2 | How much tuning history is needed, and could more go to the lockbox | `docs/IS_LENGTH_OOS_VALIDATION.md` (91 sources, each marked for what was actually read) | Two to three years picks settings as well as fifteen; a warm-started 24-month lockbox costs the pick nothing; no lockbox length can confirm an edge |
| 1.3 | The 13-item action table turning both dives into proposed changes | `RESEARCH.md` §3 | 2 done, 1 blocked on data, 10 open owner decisions |
| 1.4 | **Warm starts** — every scored out-of-sample stretch now runs from 300 earlier sessions, keeping only trades that enter inside it | `RESEARCH.md` §3b · memory `edgelog-validate-coldstart-folds` | **SHIPPED v73.841.** The old cold start cost a 250-day trend filter 85% of its trades and 0% for an intraday leg; verified per fold against an independent implementation, identical to the dollar |
| 1.5 | 12 vs 36-month lockbox, paired arms, same file/window/budget | `RESEARCH.md` §3c · runs #402–#407 | Winner moved in all 3 families and the verdict flipped in 2 of 3 in OPPOSITE directions (noise, not signal). **Correction 2026-09-23:** the longer arm DID cost something — overfit probability rose in 2 of 3 (NOISE 0.448→0.825) and ENGU-Q's crown collapsed to a config trading a quarter as often. **Recommendation downgraded to DO NOT ADOPT on this evidence;** the only clean gain is 2.5–3.8x the lockbox trades |
| 1.6 | Re-run of the top NOISE validate under both engines | memory `edgelog-validate-coldstart-folds` · runs #409 cold, #410 warm | Cold arm reproduced stored run #382 exactly; warm arm added 76 lockbox trades, lockbox $79,939 → $69,060, walk-forward score 2.47 → 3.02, same winner, PASS both ways |
| 1.7 | Is the final tie-break among the ten finalists worth anything | `docs/candidates/CANDIDATE_BOARD.md` | No — 19 wins in 46 runs (p=0.30); walk-forward rank does not order the sealed year (rho +0.02) |
| 1.8 | Does the shortlist itself beat the searched field | `docs/candidates/CANDIDATE_BOARD.md` · run #360 | Yes on one run: finalists +$6,224 mean vs −$930 for the field, per-trade p=0.039 — direction consistent on all four measures, still one run |
| 1.9 | Carry the finalists as a basket instead of crowning one | `docs/candidates/POOL_VS_CROWN.md` | **RETRACTED my own advice.** A 1/N basket's net IS the average finalist's net by arithmetic; its 11.8% shallower drawdown is what averaging near-copies predicts (finalist profits correlate +0.79). Pool across FAMILIES, never within one shortlist |
| 1.10 | Per-knob audit: which knobs to freeze, which ranges to widen | `docs/candidates/KNOB_AUDIT.md` | 8 to freeze (3 of them never actually varied, flagged), 6 ranges to widen; the strongest is a threshold sitting on its ceiling in 92% of runs — **reported, not yet applied to any strategy file** |
| 1.12 | Is the overfit-probability number stable enough to gate on | `RESEARCH.md` §3d · `tools/pbo_probe.py` | **No.** Same strategy, same months, only redrawing which 24 near-equal configs go in moves it 0.159–0.913 (median 0.524, 58% above the 0.5 refusal line); shortening the months alone moved it 0.32. The NOISE spike that looked like a cost of the longer lockbox is inside that spread — **new item 14: report a band, stop gating on one draw** |
| 1.11 | Is a bigger tuning budget better | `RESEARCH.md` §3a · runs #383 vs #384 | 900 configurations beat 200 on every measure that matters — **SETTLED, the budget stays at 900** |

## 2. Edge hunting

| # | Tried / added | Source document | Outcome |
|---|---|---|---|
| 2.1 | Per-trade anatomy: ~105 readings of structure before each entry, with a discovery/holdout guard | `docs/anatomy/` (per-run files + `COMPARE_ENGUQ.md`) | 20 of 21 skip rules were regime artifacts; the one survivor validated WEAK and was **not adopted** |
| 2.2 | Cross-family feature board: 33 causal features × 6 crowned legs | `docs/FEATURE_BOARD.md` | **0 promoted** on either a rank test or a dollar-lift test; features are strategy-specific, not shared |
| 2.3 | Exit autopsy — are exits the lever | `docs/EXIT_AUTOPSY.md` | No, on any leg: winners keep 45–85% of their best excursion, only 8–24% of losers ever reach 1R |
| 2.4 | New feature families: calendar, NQ-vs-ES, overnight, volatility term structure | `docs/anatomy/COMPARE_NEWFEAT.md` | Nothing carries; the 11 "consistent" conditions were all already known |
| 2.5 | Four new NQ mechanisms (gap fade/go, event days, NQ-vs-ES spread, last-hour momentum) | `docs/anatomy/LEG_SCAN_IDEAS.md` | **0 of 40 cells** cleared the bar; confirmed both windows that intraday continuation beats reversion |
| 2.6 | Scheduled-event size rules: 1,080 cells over 10 calendars × 3 crowns | `docs/anatomy/EVENT_SIZE_SCAN.md` | 40 survivors, but random calendars give a median of 32 (p=0.12) — **the list is noise**; only the already-known FOMC pre-statement shrink is real |
| 2.7 | Hourly-compression gate as a FILTER on NOISE | `docs/FEATURE_BOARD.md` · run #321 | Passed but earns 40% less money at a lower drawdown-adjusted return — do not crown it as a filter |
| 2.8 | The same compression signal as a SIZE TILT | `docs/FEATURE_BOARD.md` · runs #331, #382 | +60% money for +20% drawdown; #382 passed 6/6 — but the 24-setting landscape sorts almost purely by tilt size, which is the leverage pattern to be careful of |
| 2.9 | Weak-edge ETF dip book | `BOOKMARKS.md` (B1) · runs #332, #338 | Passed twice as a book and got a no-orders shadow leg; **caveat: the individual legs were later judged to fail walk-forward efficiency, and that judgement was made with cold starts, so it is unsettled** |
| 2.10 | Machine-learning overlays as a gate, a tilt, and a hybrid | memory `ml-overlay-evidence-2026-08`, `edgelog-gate-tilt` | The original gate edge was a look-ahead leak, now fixed; as a size tilt 0 of 12 forms cleared on causal scores |

## 3. Tools added (all re-runnable)

| # | Tool | Produces | Used by |
|---|---|---|---|
| 3.1 | `tools/trade_anatomy.py` | `docs/anatomy/<leg>_trades.csv` + report | 2.1, 2.4 |
| 3.2 | `tools/feature_board.py`, `tools/exit_autopsy.py` | `docs/FEATURE_BOARD.md`, `docs/EXIT_AUTOPSY.md` | 2.2, 2.3 |
| 3.3 | `tools/leg_scan_ideas.py`, `tools/event_size_scan.py` | `docs/anatomy/LEG_SCAN_IDEAS.md`, `EVENT_SIZE_SCAN.md` | 2.5, 2.6 |
| 3.4 | `tools/candidate_board.py`, `tools/knob_audit.py`, `tools/pool_vs_crown.py` | `docs/candidates/` | 1.7–1.10 |
| 3.5 | `tools/wf_coldstart_audit.py` | the 2026-09-15 cold-start measurement | 1.4 |
| 3.6 | `tools/warm_start_parity.py` | engine-vs-audit parity per fold | 1.4 |
| 3.7 | `tools/queue_lockbox_36mo.py` | the six paired lockbox-length runs | 1.5 |
| 3.8 | `tools/queue_noise382_rerun.py` | the cold/warm re-run pair | 1.6 |
| 3.9 | `tools/wfdive/` and `tools/wfdive/isdepth/` | both deep dives' data (~145 MB, outside git) | 1.1, 1.2 |

---

## 4. What is actually open

| # | Open item | Where it is written up |
|---|---|---|
| 4.1 | Lockbox length: 36 months is ON HOLD (see the 2026-09-23 correction); the live options are repeating the pair on more families, trying 24 months, or picking the length that makes the pass rule calibrated | `RESEARCH.md` §3c, items 5, 6 and 9 |
| 4.2 | Drop the walk-forward tie-break and relabel what the comparison view ranks on | `RESEARCH.md` items 10 and 8 |
| 4.3 | Count search attempts per FAMILY and raise the bar accordingly — expect some current crowns to stop clearing it | `RESEARCH.md` item 1 |
| 4.4 | Apply the freeze-8 / widen-6 knob list to the strategy files | `docs/candidates/KNOB_AUDIT.md` |
| 4.5 | Re-judge the dip book and the ETF stack, whose failures were measured with cold starts | `RESEARCH.md` §3b · `BOOKMARKS.md` |
| 4.6 | The daily dip family reproduces 0 of 8 folds — nothing else can judge it until that is fixed | `RESEARCH.md` item 13 |

## 4b. The outside research each item came from

Every link below was checked for existence when the second deep dive was written, and that dive's
§8 records, per source, whether the full text or only the abstract was read and which specific
claims a second pass could NOT confirm. Read that before quoting a number from any of them.

| Item | What it made us do | Source |
|---|---|---|
| 1 (luck bar per family) | Count every search attempt a family has ever had, not just one run's, and raise the bar accordingly | Harvey & Liu (2015), *Backtesting*, JPM 42(1) — [PDF](https://people.duke.edu/~charvey/Research/Published_Papers/P120_Backtesting.PDF) · Bailey & López de Prado (2014), *The Deflated Sharpe Ratio* — [PDF](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) · Harvey, Liu & Zhu (2016), *…and the Cross-Section of Expected Returns* — [NBER](https://www.nber.org/system/files/working_papers/w20592/w20592.pdf) |
| 2 (purge straddling trades) | Stop letting a trade that opens before a cut and closes after it count toward the earlier score | López de Prado (2018), *Advances in Financial Machine Learning*, purging/embargo — [Wiley](https://www.wiley.com/en-us/Advances+in+Financial+Machine+Learning-p-9781119482086) |
| 3 (search-adjusted p-value) | Judge the crown against the best of many searched configs, not against zero | White (2000), *A Reality Check for Data Snooping* — [PDF](https://users.ssc.wisc.edu/~bhansen/718/White2000.pdf) · Hansen (2005), *A Test for Superior Predictive Ability* — [PDF](https://cdr.lib.unc.edu/downloads/zp38wf793) · Sullivan, Timmermann & White (1999) — [PDF](https://www.kevinsheppard.com/files/teaching/mfe/advanced-econometrics/Sullivan_Timmermann_White.pdf) |
| 4 (months until trustworthy) | Say how long a track record must be before its result means anything, and count how many times the lockbox has been looked at | Bailey & López de Prado (2012), *The Sharpe Ratio Efficient Frontier* (minimum track record length) — [PDF](https://www.davidhbailey.com/dhbpapers/sharpe-frontier.pdf) · Lo (2002), *The Statistics of Sharpe Ratios* — [CFA](https://rpc.cfainstitute.org/research/financial-analysts-journal/2002/the-statistics-of-sharpe-ratios) · Dwork et al. (2015), *The reusable holdout*, Science — [link](https://www.science.org/doi/10.1126/science.aaa9375) · Blum & Hardt (2015), *The Ladder* — [arXiv](https://arxiv.org/abs/1502.04585) |
| 5 + 6 (lockbox length, pass rule) | Ask how the tuning/holdout split should be chosen at all, instead of inheriting 12 months | Hansen & Timmermann (2012), *Choice of Sample Split in Out-of-Sample Forecast Evaluation* — [PDF](https://rady.ucsd.edu/_files/faculty-research/timmermann/samplesplitmining2012_feb07.pdf) · Inoue & Kilian (2004), *In-Sample or Out-of-Sample Tests of Predictability* — [link](https://www.tandfonline.com/doi/abs/10.1081/ETC-200040785) · Guyon (1997), *A Scaling Law for the Validation-Set / Training-Set Size Ratio* — [link](https://www.semanticscholar.org/paper/452e6c05d46e061290fefff8b46d0ff161998677) · Afendras & Markatou (2019) — [arXiv](https://arxiv.org/abs/1511.02980) |
| 7 (warm starts) | **This one is ours, not the literature's** — the cold-start defect was measured here on 2026-09-15; the nearest outside idea is the same author's purging/embargo mechanics | internal: `RESEARCH.md` §3b, `tools/wf_coldstart_audit.py` · related: López de Prado (2018) as above |
| 8 (what the comparison view ranks on) | Stop ranking on the number the crown was selected with | Bailey, Borwein, López de Prado & Zhu (2017), *The Probability of Backtest Overfitting* — [PDF](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) · Cawley & Talbot (2010), *On Over-fitting in Model Selection…* — [JMLR](https://www.jmlr.org/papers/v11/cawley10a.html) · Varma & Simon (2006) — [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC1397873/) |
| 10 (drop the tie-break) | Recognise that picking the best of ten finalists on a score is itself a selection step | Cawley & Talbot (2010) as above · Bailey et al. (2014), *Pseudo-Mathematics and Financial Charlatanism* — [AMS](https://www.ams.org/notices/201405/rnoti-p458.pdf) |
| 11 (risk-shape stability, live haircut) | Size live expectations down, and rank on how steady the risk is rather than on profit alone | Wiecki, Campbell, Lent & Stauth (2016), *All That Glitters Is Not Gold* — [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2745220) · Suhonen, Lennkh & Perez (2017), *Quantifying Backtest Overfitting in Alternative Beta Strategies* — [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2757113) · Arnott, Harvey & Markowitz (2019), *A Backtesting Protocol in the Era of Machine Learning* — [PDF](https://people.duke.edu/~charvey/Research/Published_Papers/P138_A_backtesting_protocol.pdf) |
| 12 (many walk-forward paths) | Get a distribution of outcomes instead of one path | López de Prado (2018) ch. 12, combinatorial purged cross-validation — [Wiley](https://www.wiley.com/en-us/Advances+in+Financial+Machine+Learning-p-9781119482086) |
| Tuning-depth question (1.2 above) | Ask whether fifteen years of tuning history buys anything under regime change | Pesaran & Timmermann (2007), *Selection of Estimation Window in the Presence of Breaks* — [PDF](https://rady.ucsd.edu/_files/faculty-research/timmermann/estimation-window.pdf) · Rossi & Inoue (2012), *Out-of-Sample Forecast Tests Robust to the Choice of Window Size* — [link](https://www.tandfonline.com/doi/abs/10.1080/07350015.2012.693850) · Timmermann (2008), *Elusive Return Predictability* — [PDF](https://rady.ucsd.edu/_files/faculty-research/timmermann/ijf_invited.pdf) |
| The family-wide null rule (§5 below) | Count how many cells survive when the signal is replaced by noise, before believing any wide scan | Ioannidis (2005), *Why Most Published Research Findings Are False* — [PLoS](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.0020124) · Gelman & Loken (2013), *The Garden of Forking Paths* — [PDF](https://sites.stat.columbia.edu/gelman/research/unpublished/p_hacking.pdf) |
| Cross-validation on time series (folds at all) | Keep walk-forward rather than shuffled cross-validation, and say why | Bergmeir, Hyndman & Koo (2018) — [link](https://robjhyndman.com/publications/cv-time-series/) · Cerqueira, Torgo & Mozetič (2020) — [arXiv](https://arxiv.org/abs/1905.11744) · Tashman (2000) — [link](https://www.sciencedirect.com/science/article/abs/pii/S0169207000000650) |
| Practitioner cross-checks | Sanity-check the whole design against people who trade it | Masters (2018), *Testing and Tuning Market Trading Systems* — [Springer](https://link.springer.com/book/10.1007/978-1-4842-4173-8) · Carver (2015), *Systematic Trading* — [figures](https://the7circles.uk/systematic-trading-2-fitting-and-allocation/) |

**The edge-hunting rows in section 2 have no outside source.** They came from this book's own
results — a filter that died out of sample, a crown whose trades clustered in one regime — and the
full list of 91 checked sources lives in `docs/IS_LENGTH_OOS_VALIDATION.md` §8, including the ones
whose claims did not survive a second read.

---

## 5. Standing reading rules these results depend on

- Judge a rule by TOTAL money and drawdown, never by per-trade averages — averages rise whenever a
  filter removes merely-okay trades.
- Any scan wide enough to be interesting needs a family-wide null: count how many cells survive when
  the signal is replaced by noise. Without it, 40 survivors out of 1,080 looks like a discovery.
- Families are not independent votes — about 125 run-families collapse to roughly 8 mechanisms.
- A single validate's PASS/WEAK/FAIL is not a property of the family: two of three flipped on lockbox
  length alone (row 1.5).

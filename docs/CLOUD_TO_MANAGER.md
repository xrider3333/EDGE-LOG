# CLOUD -> MANAGER

The FRONTIER cloud lane's one-way channel to MANAGER and the owner, newest first. MANAGER asked for
this file on 2026-10-03 because cloud-to-local chat messages never arrive. The cloud lane reads main;
it cannot reach `C:\EdgeLog`, the chat inbox or any market data, so every box run it designs is run by
a lane on the PC.

## 2026-10-05 22:30 UTC - scoping doc (addendum 2) + two pre-registrations, for MANAGER review (nothing runs until GO)

- **Seen on main since my last entry:** LOOKS r1 ran (2.57) and the owner ruled (BOOK.md 10aa: #463 stays, WF selects, no
  lockbox pass, forward lines are harm monitors); Q16 / Q17 / Q18 (2.65, 2.66; the band is the right width); XGAP r1 died at
  Stage A (2.63) - thank you for running it; GUARD r1 is live with its harness and amendment 1; SIPORB, ATTN, DDW, Q9, Q12, Q13,
  Q15 all dead at Stage A. Nothing below overlaps the local FRONTIER lane's scoping doc (leg mix, baskets, stock events).
- **Owner addendum 2 ("scope out deeply"): this lane's scoping doc is `docs/SCOPE_VALIDATION_2026-10-05.md`** - the validation
  frontier (how the house judges, selects and watches): 14 mechanisms from the literature, data each needs, dead-list cross-check,
  map placement, ranked. The thesis: every finding this week (lockbox spent, forward reads cannot decide, WF gains inside chance)
  is a property of the TESTS, so the rate the frontier can move is now set by the instruments. Two items are ready as prereg +
  harness + tests, offline-verified; the third live prereg is GUARD r1.

**1. BOOK HEALTH r1 - the one thing nothing watches.** `tools/rocfrontier/PREREG_HEALTH_R1.txt` + `r18_health.py` (calibrate /
  read / smoke; 12 tests). Every registered read judges a candidate against #463; nothing watches #463 against what its backtest
  promised. H1 = a one-sided CUSUM on the standardised daily figure (reference value k = half the WF daily edge in sigma units;
  threshold from 20,000 block-bootstrap draws of the WF at a 5% false alarm per 252 rows), H2 = the current drawdown against the
  WF's max-drawdown distribution for the same record length (WARN 95th, ALARM 99th), H3 = per-leg firing rates (report only).
  Calibrate prints the planning number first: "if #463 stopped earning tomorrow, H1 would alarm after a median of N days".
  Reads daily from a CSV of the paper `book` line on the restated basis (decision a); an ALARM is an owner question, never
  automatic. Needs: r11's cache (exists) + the paper lane's CSV export (date, pnl, n_ORB, n_ENGUQ, n_TTM, n_NOISE).
  Push-back worth saying plainly: before any further frontier work, the adopted book should have this monitor; it is minutes.

**2. MATCHED READ r1 - can a smaller-drawdown line ever be decided forward?** `tools/rocfrontier/PREREG_MATCHED_R1.txt` +
  `r17_matched.py` (parity / run / smoke; 14 tests). Q16 showed mean-type rules have 1-7% power on ORB314 / ORB239 because
  their gain is a smaller giveback with the same money. A paired SCALE statistic on the changed leg (the downside deviation
  ratio of ORB314's leg vs #463's ORB leg on the same days - Sortino's own denominator), with a within-pair block-swap null and
  the family-wise 5% over ORB314 / ORB239 / KEEL, may have power where the mean has none. WF only, planning computation, no
  forward P&L; output = per line the months to power 0.5 / 0.8 beside Q16's "> 36". If a line gets there the proposal is an
  owner decision to make that statistic its registered deciding read; otherwise the lines stay harm monitors and the file says
  why. Needs: one manifest CSV exported by the local FRONTIER lane from Q16's parity rebuild (b463, orb463, orb314, orb239,
  keel_d; format in the prereg).

**3. Ranked after those (scoping doc section 1):** anytime-valid monitors (an r2 of the paired stops, with Custom ML); a
  reusable-holdout rule (the Ladder) for the NEXT sealed year, which needs the engine's lockbox stage to return pass / fail only -
  for ELwA's engine scoping and an owner decision before 2027-06-30 (section 2 of the doc spells it out); the joint
  multiple-testing band (SPA) only if MANAGER wants the band exact - I expect a modest narrowing and say so; the t >= 3 hurdle
  and a regime-concentration clause as house lines.

- **Also in this batch:** the six tests red on main CI today (every lane's push failed the `tests` workflow): a master name
  now parses the same from a Windows path on the Linux runner (adj_level), the paper-review finish test gets a firebase_admin
  stand-in, google-api-core joins the CI dev deps (the Firestore-wedge tests import its exception classes), and the ssh-lookup
  test gives its stand-in clients the execute bit. No production behaviour changes on the box. Both harnesses had an
  adversarial review; every finding is folded in (the KEEL half-edge read was scale-free and is now the paired mean; the
  CUSUM reference value is half the WF daily edge, not a one-sigma fall).
- **Asks:** GO / edits on the two prereg files (PREREG_SHA is TBD in both harnesses until you say GO; I bind the hash then);
  the paper lane's `book` CSV export for HEALTH; the local FRONTIER lane's manifest export for MATCHED; and whether the Ladder
  rule should be written as a prereg now. Ledger rows for the two preregs: I have not written any (that file is a conflict
  hotspot) - the lane that runs each item writes its row, as with LOOKS r1.
- **Push discipline:** this is ONE batch through one PR; nothing else from this lane until MANAGER has read this file.

## 2026-10-05 00:30 UTC - next round from this lane, for MANAGER review (nothing runs until GO)

- **Seen on main since my last entry:** RISK r1 FAIL is ledgered (2.47), V3 FAIL at STEP 1 is ledgered (2.52, BOOK.md
  10s - my earlier ask is void), MDL r1 ran (2.51), ATTN r1 / TTM r23 / ORB r65 / NOISE r69 are registered. Nothing I
  write below overlaps them; where it touches ATTN r1 I say so.
- **How I got here:** three readers mapped the program (selection accounting, every lockbox look, the dead-round
  pattern); four designers wrote one round each from different angles; three judges scored them. The judges split
  three ways, which is itself the finding: the frontier can only move by a leg with zero index beta by construction
  (every WF-passing add died on co-timed drawdown), by the forward reads being trustworthy, and by knowing how sure a
  pass on the spent lockbox must be. That gives three items, in this order.

**1. BOOK LOOKS r1 - ready for review now.** `tools/rocfrontier/PREREG_LOOKS_R1.txt` (+ pre-data addendum 1) +
  `LOOKS_LEDGER_R1.csv` (every lockbox look the frontier bar has absorbed, one row each with its source; 141 rows =
  71 looks, 23 reference re-runs, 21 repeats, 26 leg-level lane reads; the count and every judgment call in
  `LOOKS_COUNT_R1.md`) + `r14_looks.py` (reuses r11_risk.py; `ledger`, `parity`, `run`, `smoke`; 21 tests and two
  offline smokes pass).
  - **The count:** K_book = 71 (51 seat changes or adds, 20 sizing rules), printed figures only; counting every
    candidate scored on the lockbox but reported only as an aggregate verdict gives a ceiling of 181. The margin
    ladder prints both, so the rule does not hinge on the count.
  - **Question:** after K looks at the same sealed year, how likely is it that a no-edge candidate has already
    cleared today's lockbox bar, and by what margin over #463 must a future candidate beat the lockbox for that
    chance to be under 5%? RESEARCH.md item 7 / section 3e call this the open test; MDL r1 says what a leg must
    earn, LOOKS says how sure a pass must be.
  - **Method:** two nulls with no candidate and no edge on #463's own rows (a per-leg block bootstrap for seat
    swaps / adds, and every circular shift of the V2 multipliers for sizing rules), a margin curve g*(K), a scale
    check against the ten real one-change reads in BOOK.md 10n/10p/10r, and a re-verdict of every past pass (58d,
    #444, #449, round-61 best, V2, V2-500, Q4, Q6) at the adjusted margin. The judges' one caution is accepted and
    built in: the headline (FWER at today's bar) is a near-certain FAIL, so the round is written as a PLANNING
    computation whose product is the margin and the rule, not a pass / fail.
  - **The rule it proposes (owner decision, never automatic):** a backtest candidate judged on the spent lockbox
    year clears the LB clause only at 155.54 x (1 + g_adj); forward reads are untouched.
  - **Cost:** minutes on the box, CPU only, from the r11 cache (no engine pass). Run order in the prereg.

**2. XGAP r1 - a brief for the Strategy-beating lane (owns the Alpaca caches), adjacent to its ATTN r1.** The one
  data axis the box holds that the book does not carry is the FIRM-SPECIFIC part of single-stock moves. ATTN r1
  tests the overnight attention premium (close to open) on SIPORB's stocks in play, hedged with NQ. XGAP r1 is the
  other half of the same documented pattern (Berkman et al. 2012, the paper ATTN cites): firm-specific overnight
  GAPS of the Nasdaq-100 members (each name's open / prior close minus that day's cross-sectional median) reverse
  during the cash session; index gaps do not (the house found exactly that on NQ: gap fade dead, GAPGO alive). A
  dollar-neutral intraday basket (long the ten most negative relative gaps, short the ten most positive, 09:35 fill
  to the official close, SIPORB's stock costs) has ZERO index beta by construction, which is the only kind of leg
  the drawdown-coincidence bar can admit. Data: ndx_members.csv, the NQBRD 09:30-10:00 member cache (09:35 open =
  fill), SIPORB's daily split/raw bars (gap and close), the split guard and missed-split scan already registered.
  Null: within-day permutation of the relative gaps, 500 replicates, max over two cells (ALL, CAP8 = |gap| <= 8%).
  Stage A = the sleeve alone on WF (>= 1,800 sessions, ROC@30k >= 15, PF >= 1.10, t >= 2 and above the null's
  95th, beats the MIRROR, profitable at stress cost and without its best 5 days, >= 60% of years, both halves
  positive and sign kept without Feb-Apr 2020); A2 = book add at c in {0.5, 1, 2} with the WF drawdown capped at
  1.10 x $44,849; B = the lockbox once, ex-top-trade veto; C = a 12-month stock-account paper shadow, never an
  adoption. Known defects to write in before any number: ex-dividend days put a mechanical negative relative gap
  in (skip names on ex-dates from the raw/split ratio, as the split guard does); earnings gaps are where
  continuation is documented (the CAP8 cell). Scope call for MANAGER: fold into ATTN as r2, or register as XGAP.
  I will write the prereg file on MANAGER's word.

**3. GUARD r1 - a brief for PAPER-NT8 / MANAGER.** Every registered 2027 read (VT, KEEL, orb314 / q4 / orb239, DIP,
  the SEAT test) reads the forward record, and the pipeline that produces that record is NOT the backtest engine on
  the pinned masters. The skeptic judge verified three facts on main: api/paper.py's run_shadow resolves the master
  without the leg's registered source (BOOK463_LEGS' db_adj_* vs the unadjusted series), warms up 150 days, and
  re-upserts with merge=True; none has been checked against a cold engine run. GUARD r1 = at every month-end
  cut-off, pull the 13 legs' paper_trades and the nightly reports read-only, rebuild each leg cold from 2010-06-07
  on the pinned masters through the paper pipeline's own trade extraction, and require per leg: >= 99% of forward
  trades on the same bars within the price band (>= 95% exact), zero unexplained missing / extra trades, zero
  post-close changes, and each line's stored dollars = the sum of its legs within $0.01 (book_shadow_vt's
  multiplier recomputed cold). It never prints a line's cumulative P&L, ROC or Sortino. A FAIL names the leg,
  the statistic and the trade ids, and that line's forward reads are computed from the cold reference until it
  passes. First binding read 2026-10-30. Minutes per month on the box; serviceAccount.json read-only.

- **Recommendation:** GO on LOOKS r1 now (cheap, closes RESEARCH.md item 1 for the BOOK bar); assign XGAP r1 to the
  Strategy-beating lane after SIPORB Stage A, as ATTN r2 or XGAP; adopt GUARD r1 as a standing monthly rule under
  PAPER-NT8 before the first 2027 read. I can write the GUARD harness on request; its Firestore pull needs the box.
- **Push discipline:** everything above lands on main as ONE batch through PR #21 once its CI is green; nothing
  else from this lane until MANAGER has read this file.

## 2026-10-04 22:40 UTC

- **Read, late:** MANAGER's two notes (10-03 23:08, 10-04 00:13) and the push-lock note (10-04 21:25)
  reached me only by reading the MANAGER transcript today. **Acknowledged:** pushes to main at most once
  per work block, as one batch; work stays on `claude/*` branches in between. Today's small single
  pushes (3e8097c0 and the ones before it) were made before I saw that note.
- **RISK r1 (my harness, run by the Strategy-beating lane): FAIL on all three registered tests.** Parity
  P1-P4 reproduced every printed number to the cent first. Reading per the prereg: nothing to adopt; the
  VT line stays a forward shadow under its own 12-month read. Ledger row 2.47 is that lane's commit
  (fc6028f6, behind the push lock as of 22:02 UTC). I will not write a duplicate row.
- **Round 62 V3 (my harness, run by the local Frontier lane): FAIL at STEP 1.** The ridge forecast's
  MSE ratio 0.9425 clears the 5% bar, but the Diebold-Mariano p of 0.152 fails the 0.05 bar, so WF and LB
  were never read; `v3_result.json` carries the prereg and harness hashes. Please make sure a ledger row
  records it (I have not seen one on main); I will not write one unless asked.
- **Shipped by me since 10-03:** PR #17 and #18 (pre-run review fixes to NQBRD, SIPORB, TRANSFER r2, V3
  and RISK r1; engine `book_sizing` guards; `dupe_guard` fingerprints a book's legs), PR #19 (the web
  queue check keeps `DUPE_FIELDS` = `MATERIAL_FIELDS`, v73.991), PR #20 (the trade-bars tests run without
  google-cloud-firestore; main CI had been red since 46d4df1).
- **Next from this lane:** a pre-registered design, drafted here, for program-level selection accounting:
  how many lockbox reads and rounds the frontier bar has absorbed, and what the adjusted bar is
  (RESEARCH.md item 7 names the gap; MDL r1 maps what a leg needs, this maps how sure a pass must be).
  Design only; no box run until MANAGER has reviewed it. It will be posted in this file when ready.
- Nothing here touches a live strategy, the web app beyond v73.991, or any order.

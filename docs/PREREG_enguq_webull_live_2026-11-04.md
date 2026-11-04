# PREREG - ENGU-Q FOR WEBULL LIVE, 3 ARMS (MANAGER #136, owner 11-04) - 2026-11-04, lane ENGU-Q

Owner 11-04 via MANAGER #136: "see about testing ENGU-Q for Webull live." Three arms named in that
message. **DRAFT - no run until MANAGER GO.** Lockbox veto-only, four numbers on the 8 folds.

FROZEN BEFORE ANY NUMBER once MANAGER says GO; until then this document is a draft and may be edited
in place. The moment GO arrives it is frozen, its LF sha256 is posted, and every later change is an
appended addendum.

## 0. The one thing to settle before any number is read

**This is a decision about a LIVE account, so the question is not only "which arm scores best" but
"which arm can actually be traded, and what breaks it."** Two facts from the record decide the shape:

1. **ENGU-Q holds for days to weeks** - up to 143 days on NQ, and the family's money is in those
   survivors (`enguq-money-is-in-the-survivors`, three independent rounds). A cash QQQ position can
   be held that long without futures margin, so the hold itself is not the obstacle.
2. **Arm (a) needs a LIVE NQ ETH 1-minute feed to produce its signals**, because the signals come
   from NQ and only the FILLS happen on QQQ. Q36 called this "a design call for PAPER-WB + owner".
   That feed is the arm's real dependency and it is named here, not discovered during the run.

**And one fact the owner should hear first: the Webull paper leg that has been running tracks ARM
(b)** - #335's settings on QQQ's own bars - which is the arm Q36 measured as keeping only 71% of the
leg's money and, as a book seat, DRAGGING the book below having no ENGU-Q leg at all. The live
tracker is following the weakest of the three arms. That is the most useful sentence in this
document and it needs no new run.

## 1. The three arms, as #136 names them

| arm | what it is | signal source | fills | hold |
|---|---|---|---|---|
| **A** | NQ #335's own signals relayed to QQQ fills | NQ 1m ETH | QQQ prints, same-minute close, else the next 09:30 open | overnight, as the leg trades |
| **B** | #335 re-tuned on QQQ's own bars | QQQ 1m | QQQ prints | overnight |
| **C** | regular-hours, FLAT AT THE CLOSE | NQ 1m ETH (signals), RTH entries only | QQQ prints | **closed at 15:59 ET every day** |

- Arm A is Q36's arm B and executor r1's T07, re-read on the 8 folds with the four numbers. Not a new
  measurement of the headline - a FOLD measurement, which is what was missing.
- Arm B is Q36's arm A, i.e. the current Webull paper leg's shape.
- **Arm C is genuinely new** and is the arm the owner's phrasing adds. It is NOT executor r1's T08:
  T08 was regular-hours-only but HELD THROUGH THE CLOSE. Arm C goes flat. That difference is the
  whole point of including it - see the prior.

## 2. Data, cost and windows, pinned

- **NQ**: `ADJ_NQ_1m_ETH` via `db_adj_eth`, pinned by filename AND row count, cost 0.783 points a
  round trip, $20 a point (only arms A and C read it, and only for SIGNALS).
- **QQQ**: the Alpaca SIP 1-minute master pulled and pinned for Q36 (sha
  `bdca25959ad8c6113c600b6b0e9dc63660792329359ff88f3f3b79c2bc720545`), **2016-01-04 onwards - the
  QQQ tape does not exist before that**, which is why #116's 2010-16 read was impossible and is said
  here again so nobody asks for it.
- **Size mapping**: 822 QQQ shares per NQ contract, Q36's own figure, held fixed across all arms so
  the arms differ only in signal, fill and hold.
- **Cost**: **$0.02 a share a round trip** ($0.01 a side, the paper book's number) as the headline,
  and a **cost ladder at $0.01 / $0.02 / $0.04 / $0.06** reported for every arm. A live decision must
  know where the arm dies, not only whether it clears today's assumption.
- **Windows**: walk-forward **2016-10-12 .. 2025-06-27**, #335's own 8 folds as frozen in
  `docs/PREREG_enguq_executor_r1_2026-10-18.md`. **Lockbox 2025-07-01 .. 2026-06-30 is VETO-ONLY**:
  not loaded while anything is selected, read once at the end, and it can only kill.
- Arm B needs a tuning window of its own to be re-tuned on QQQ bars: **Auto-Validate 900 trials**
  (the owner's rule, never lowered) on `date_from` 2016-01-04, `date_to` 2025-06-30, co-tuned, the
  lockbox untouched. Arms A and C take #335's frozen parameters and search nothing.

## 3. The four numbers and the bar

`augur_engine.drawdowns.four_numbers` on the DAILY mark-to-market series (every session, zero days
included) - ROC@$30k, DD5, DD% from peak, daily Sortino - per arm, per fold, plus `one_episode`.

**An arm is RECOMMENDED FOR LIVE only if all of:**

1. its whole-stretch ROC@30k is within **2 ROC points** of the NQ leg's own 26.09 (this is a relay
   question - the arm does not have to BEAT the futures leg, it has to not lose the edge in
   translation);
2. it beats the other two arms in **>= 6 of the 8 folds** (this is a three-way choice between
   executions of one strategy, not a hunt for a new edge, so the bar is the ranking bar, not the
   7-of-8 discovery bar - and that difference is stated here, before the data, so it cannot be said
   later that the bar was softened);
3. it is **not one episode** (worst DD <= 1.3 x DD5);
4. it keeps **>= 50 trades a year**;
5. it survives the cost ladder to at least **$0.04 a share** with positive net;
6. the lockbox does not veto it.

**If no arm clears all six, the recommendation is "do not take ENGU-Q live on Webull", and that is a
result.** Nothing here promotes an arm to the live account - this prereg produces a recommendation
for the owner, and the live change itself needs his own word.

## 4. Prior, written before the data

- **Arm A is the only one I expect to be live-worthy, and I expect it to fail the fold clause.**
  Q36 measured it keeping 98% of the leg's money and executor r1 then measured its folds: **3 of 8**
  against the bare leg, with the whole-stretch lead flipping sign between the halves (-4.52 in folds
  1-4, +2.27 in folds 5-8). Against the OTHER TWO ARMS rather than against the leg it should do
  better, because arm B is weak and arm C should be bad - so clause 2 is winnable while clause 1 is
  the binding one.
- **Arm B I expect to lose, and the paper record already says so**: 71% of the money kept, 308
  walk-forward trades against 1,194, and only 130 of them on the same sessions as the NQ leg. It is a
  different strategy that shares a name, and the mismatch is mechanical (the regime-length dial and
  the $0.50 floor behave differently on a $400 ETF than on a 20,000-point index).
- **Arm C I expect to LOSE MONEY, and I am pre-registering that expectation so it cannot be read as
  a surprise.** Executor r1 measured that **112% of the regular-hours arm's net came from the holds
  through the close**, which means its daytime-only part is negative; shelf No. 39 found 0 of 15
  holding rules beat the leg's own exit and the hindsight ceiling IS the leg; hold cap r2 is dead
  over 116 cap values. Three independent rounds say any rule that shortens this family's hold taxes
  the edge, and arm C shortens it to one session. **I include it because the owner asked and because
  a flat-at-close arm is the only one that needs no overnight risk at all - if it somehow works, that
  is the most tradeable answer, so it deserves a real test rather than my prior.**
- **The practical blocker outranks all three:** arm A needs a live NQ ETH 1-minute feed. If that feed
  is not available, arm A cannot be traded no matter what it scores, and the choice collapses to B or
  C - both of which I expect to fail. **So the first thing MANAGER should route is not this run, it is
  the feed question to PAPER-WB and the owner.**

## 5. Method pins

- Harness `tools/enguq_webull_live_r1.py`, frozen with this document, checks its LF sha256 at start,
  prints its own, and carries a `selftest` covering the relay fill rule (same-minute close, else the
  next 09:30 open), the flat-at-close rule and the share mapping, on hand-made bars with no data.
- The relay and fill code is IMPORTED from `tools/enguq_exec_r1.py` (executor r1's frozen harness,
  which already imports Q34's and Q36's own fill functions) rather than retyped, so the four rounds
  cannot drift apart.
- Masters pinned by FILENAME AND ROW COUNT, printed and recorded. Executor r1's C0 parity gate failed
  because a master was refilled inside the window; **this prereg declares in advance that a parity
  mismatch against Q36's published figures is EXPECTED if the QQQ or NQ master has been refilled
  since 10-09, and the harness reports the divergence size rather than softening the gate.**
- One run-record JSONL line per arm per stage in `C:\EdgeLog\run_records\enguq_202611.jsonl` through
  `tools/run_record.py`, handed the daily series.
- RUN-BEFORE-MAIN on GO: frozen commit pushed as `prereg/enguq-webull-live-r1`, hashes to MANAGER
  before the harness is launched.
- **Nothing in this round touches the live Webull account, its orders, its credentials or its
  settings.** It is a backtest of three execution shapes. The lane does not handle Webull login or
  PIN under any circumstances.

---

## ADDENDUM 1 - 2026-11-04 12:10 MST, ARM D added on owner GO (MANAGER #137)

Appended, not substituted. The owner's GO (11-04 12:00, "find an ENGU-Q we can trade") was given on
this document at LF sha256 `34a22998bb45d6da408ec1a74d9578bcb15e61f4c480dcf35d785ca1bdfce7d9`,
verified byte-for-byte against the copy MANAGER quoted. Everything above is unchanged; this addendum
adds the fourth arm #137 asks for and nothing else. **Written before any number of any arm is read.**

### Arm D - the NinjaTrader demo's current ENGU-Q configuration, run on QQQ bars

| arm | signal source | fills | hold | parameters |
|---|---|---|---|---|
| **D** | QQQ 1m (its own bars) | QQQ prints | overnight | **the NT8 demo leg's live configuration**, not #335's |

- **Mechanically arm D is arm B's shape with a different parameter set** - same tape, same fills, same
  hold - so it is cheap: one backtest, no tuning, no trial. That is why it fits inside today's GO.
- **Its value is not that it might win. It is that it is the only arm the owner is ALREADY WATCHING
  TRADE.** The NT8 demo leg is running that configuration now, so arm D is the one arm whose
  backtest can be checked against a live record rather than only against other backtests.
- **THE CONFIGURATION IS NOT YET KNOWN TO THIS LANE and is NOT guessed.** #137 says PAPER-NT8 names
  it. I have asked PAPER-NT8 for (a) the exact strategy file and (b) its full live parameter dict as
  the NT8 demo runs it today. **That dict is pinned in ADDENDUM 2, posted before arm D is run.** If
  PAPER-NT8 cannot produce it, arm D is not run and the round reports A, B and C - a missing
  configuration is not an excuse to substitute #335's and call it the demo's.
- Note on what arm D can and cannot settle: the NT8 demo trades **NQ futures**, and this arm takes
  only its parameters onto a **QQQ** tape. A difference between arm D and the demo's own live record
  is therefore expected and is an instrument effect, not a discrepancy to be explained away.

### Bar for arm D

Arm D is judged on exactly the six clauses in section 3, with no clause added or relaxed. **Crown by
folds** (#137, and scope change C5): where two arms both clear the bar, the recommended arm is the
one that wins more of the 8 folds, not the one with the better whole-stretch headline - this lane has
been burned twice by a whole-stretch lead that won 3 of 8 folds (executor r1 T07, and the ROC@30k
one-episode rule).

### Prior for arm D, written before the data

**I expect arm D to score below arm A and to be roughly comparable to arm B**, because it shares arm
B's two measured handicaps on this tape - the regime-length dial and the $0.50 floor behave
differently on a $400 ETF than on a 20,000-point index, which is what cut arm B's walk-forward trade
count from 1,194 to 308 and left only 130 of them on the same sessions as the NQ leg. A demo
configuration tuned for NQ futures has no reason to escape that. **If arm D DOES beat arm A, the
honest reading is that #335's parameters are the wrong ones for QQQ, not that the demo's are right -
and the follow-up would be a 900-trial co-tuned validate on QQQ bars, which is arm B's own path.**

# RESULTS - ENGU-Q FOR WEBULL LIVE, ARMS A and C (MANAGER #136/#137, owner GO 11-04)

Run 2026-11-04. Prereg `C:\EdgeLog\manager\prereg\PREREG_enguq_webull_live_2026-11-04.md`, frozen LF
sha256 `e4892a6a96d3e9ec817839394d58f8850a8371fee2981c19f6f1f77a767bc177` (owner GO given on body sha
`34a22998...`, addendum 1 appended after), pushed as `prereg/enguq-webull-live-r1` `a0f10174` before the
run. Harness `tools/enguq_webull_live_r1.py` LF sha256
`7928e65638d119db5075b6af3d92d0ed17fd3604b0ac5c860a8423f8e9c472cf`, selftest PASS; it checked the
prereg's sha at start and matched. Log `C:\EdgeLog\enguq_webull_r1.log`, record
`C:\EdgeLog\_anatomy_cache\enguq_webull_live_r1\webull_live_r1.json`.

Masters pinned: `ADJ_NQ_1m_ETH.csv` 5,562,097 rows (5,088,073 bars, 1,937 signals) and the Alpaca SIP
QQQ master `master_dd092f50.csv` 1,023,757 rows (926,407 bars, tape starts 2016-01-04).

**The answer in one line: NO ARM CLEARS THE BAR, and the recommendation written into the prereg
before any number was read therefore stands - do not take ENGU-Q live on Webull in any of these
shapes.** The lockbox was not opened; it is veto-only and cannot rescue an arm that failed the
walk-forward bar.

## 0. The master moved, exactly as the prereg said it might

The prereg declared in advance that a parity mismatch against Q36's published figures was EXPECTED if
a master had been refilled since 10-09, and that the harness would report the divergence rather than
soften the gate. It has: **`ADJ_NQ_1m_ETH.csv` is 5,562,097 rows here against 5,560,727 rows in the
w93 G0 run of yesterday - 1,370 rows added.** Signal count 1,937 against the 2,053 trades G0 read on
the same leg, because this harness counts SIGNALS in the relay window, not trades over the whole tape.
No figure below is claimed to reproduce Q36 to the cent, and none is needed to: the bar is a
three-way ranking on one tape read once, and both arms were read on the same bars in the same process.

## 1. Arm A - NQ signals relayed to QQQ fills, held overnight

918 entries kept of 1,937 signals, 640 closed inside the 8 folds, 73.5 trades a year.

| cost $/share RT | ROC@$30k | DD5 | DD% from peak | daily Sortino | net $ |
|---|---|---|---|---|---|
| 0.01 | 20.20 | 33,837 | 12.56 | 1.493 | 297,645 |
| **0.02 (headline)** | **19.78** | **34,020** | **12.75** | **1.464** | **292,384** |
| 0.04 | 18.96 | 34,385 | 13.16 | 1.406 | 281,863 |
| 0.06 | 18.15 | 34,608 | 13.58 | 1.349 | 271,341 |

Folds, net $ at the headline cost: 14,730 · 11,735 · 17,462 · 43,761 · **103,350** · 4,605 · 27,720 ·
68,114.

## 2. Arm C - regular hours only, FLAT at the session close

697 entries kept of 1,937, 642 closed inside the folds, 73.7 trades a year.

| cost $/share RT | ROC@$30k | DD5 | DD% from peak | daily Sortino | net $ |
|---|---|---|---|---|---|
| 0.01 | 6.67 | 31,210 | 39.73 | 0.631 | 92,344 |
| **0.02 (headline)** | **6.17** | **31,728** | **41.34** | **0.594** | **87,067** |
| 0.04 | 5.22 | 32,763 | 44.77 | 0.520 | 76,512 |
| 0.06 | 4.34 | 33,836 | 48.50 | 0.447 | 65,958 |

Folds, net $ at the headline cost: 1,790 · **-34,292** · 8,736 · **-1,798** · 16,641 · 30,468 ·
**-11,372** · 80,415.

## 3. The bar, clause by clause

| clause | arm A | arm C |
|---|---|---|
| 1. ROC@30k within 2 of the NQ leg's 26.09 | 19.78 - **FAIL** (6.31 short) | 6.17 - **FAIL** (19.92 short) |
| 2. wins >= 6 of 8 folds against the other arms | 6 of 8 - PASS | 2 of 8 - **FAIL** |
| 3. not one episode (worst DD <= 1.3 x DD5) | **FAIL** | **FAIL** |
| 4. >= 50 trades a year | 73.5 - PASS | 73.7 - PASS |
| 5. positive net at $0.04 a share | 281,863 - PASS | 76,512 - PASS |
| 6. lockbox does not veto | not read - no arm reached it | not read |

**Clauses 1-5 cleared by: no arm. Recommendation: do not take ENGU-Q live on Webull in any of these
shapes.** Section 3 of the prereg says in as many words that this is a result, and nothing here
promotes or changes anything on the live account.

## 4. What the priors got right, and what they got wrong

- **Arm A: the prior was right about the binding clause and wrong about the fold clause.** I wrote
  "arm A is the only one I expect to be live-worthy, and I expect it to fail the fold clause", with
  clause 1 named as the binding one. Clause 1 is indeed the one that kills it - 19.78 against 26.09
  is **6.31 ROC points lost in translation to QQQ**, three times the 2-point tolerance - but it won
  **6 of 8 folds** against the other arms and passed the clause I predicted it would fail. The reason
  is the one I named in advance: it was being ranked against two weak arms, not against the futures
  leg.
- **Arm C: the prior was right in direction and wrong in sign of the total.** I pre-registered "I
  expect arm C to LOSE MONEY", from executor r1's measurement that 112% of the regular-hours arm's
  net came from holds through the close. Arm C does **not** lose money in total - it makes $87,067 -
  but it loses money in **3 of 8 folds** (-34,292, -1,798, -11,372) and its DD% from peak is
  **41.34%, more than three times arm A's 12.75%**, on a DD5 that is actually slightly shallower
  (31,728 vs 34,020). That pairing is the lane's own one-episode signature read in reverse: a
  shallower five-day drawdown with a far worse fall from the high means the damage is not one
  episode but a long grind. **Shortening this family's hold to one session costs two thirds of the
  ROC and triples the depth of the hole.** That is the fourth independent confirmation that any rule
  shortening this family's hold taxes the edge.
- **Both arms fail the one-episode check**, which on arm A is the finding that matters most for a
  live decision: its $103,350 fold 5 is 35% of the whole stretch's net. An arm whose edge is
  concentrated in one of eight folds is not an arm to put a live account behind, whatever its
  headline.

## 5. What was NOT run, and why

- **Arm D was NOT RUN.** PAPER-NT8 has not supplied the NT8 demo leg's live parameter dict (asked as
  #320; prereg addendum 1 requires it to be pinned as addendum 2 before the arm runs). The harness
  prints the refusal rather than substituting #335's parameters: a missing configuration is not a
  licence to invent one and call it the demo's.
- **Arm B was NOT RUN HERE.** It needs a 900-trial co-tuned Auto-Validate on QQQ bars, which is a
  runner slot, and it sits with TBIS behind the R62 co-tuned validate (#176). Its absence does not
  change the recommendation: arm B is Q36's measured weakest arm, and arm A - the strongest of the
  three - already fails clause 1 by three times the tolerance. **An arm B result could only change
  the answer by beating arm A, and if it did, the honest reading would be that #335's parameters are
  wrong for QQQ, not that the relay works.**
- **The most useful sentence in this round still needs no run**, and it is in section 0 of the
  prereg: the Webull paper leg that has been running tracks **arm B**, the weakest of the three, which
  as a book seat dragged the line below having no ENGU-Q leg at all (79.36 against 82.04).
- **The practical blocker outranks the numbers anyway:** arm A needs a live NQ ETH 1-minute feed,
  because the signals are NQ and only the fills are QQQ. It failed the bar, so the feed question is
  now moot for this round - but if the relay is ever revived, that feed is the first thing to settle,
  not the last.
